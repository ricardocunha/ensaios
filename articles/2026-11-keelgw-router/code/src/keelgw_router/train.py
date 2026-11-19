"""Trains the router's four-Tier head.

Embeds the train, val and eval splits of dataset/prompts.jsonl with the pinned
embedding model (classifier.py), fits a multinomial logistic regression on
train, picks its L2 strength on val by macro-F1, and reports accuracy per
Tier, macro-F1 and the confusion matrix on eval, plus CPU latency per request
(one request at a time, batch size 1) on this machine. Writes model/head.json
and model/metrics.json.

    uv run python -m keelgw_router.train                     # the real head, from dataset/prompts.jsonl
    uv run python -m keelgw_router.train --from-generated    # a provisional smoke run on dataset/generated-raw.jsonl

--from-generated labels each prompt with the Tier it was generated for (no
relabel, no review) and writes model/head.provisional.json and
model/metrics.provisional.json, which git ignores: they are for trying the
image, never the shipped head.

Embeddings are cached in .cache/embeddings (git-ignored), keyed by the model
revision and the text, so a rerun after a review only embeds new prompts.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import platform
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import classifier as c

ROOT = c.ROOT
PROMPTS = ROOT / "dataset" / "prompts.jsonl"
RAW = ROOT / "dataset" / "generated-raw.jsonl"
EMB_CACHE = c.CACHE / "embeddings"
L2_GRID = (1e-4, 1e-3, 1e-2, 3e-2, 1e-1)
TARGET_ACCURACY = 0.80
TARGET_P95_MS = 800


# ---- data ---------------------------------------------------------------------------


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def load_prompts(path: Path = PROMPTS) -> list[dict]:
    """Rows of dataset/prompts.jsonl that have a Tier and a training split."""
    return [r for r in read_jsonl(path) if r.get("tier") in c.TIERS and r.get("split") in ("train", "val", "eval")]


def load_generated(path: Path = RAW) -> list[dict]:
    """Provisional rows from the generator's raw answers, read only: the Tier
    each prompt was written for is its label. Splits are 70/10/20 per Tier by
    a hash of the prompt."""
    from . import dataset

    by_id = {cell.custom_id: cell for cell in dataset.cells()}
    rows, seen = [], set()
    for raw in read_jsonl(path):
        cell = by_id.get(raw.get("custom_id"))
        if not cell:
            continue
        for p in dataset.parse_generated(cell, raw.get("content", "")):
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            bucket = int(p["id"][:8], 16) % 10
            p["split"] = "eval" if bucket < 2 else "val" if bucket == 2 else "train"
            rows.append(p)
    return rows


# ---- embeddings, cached on disk -------------------------------------------------------


# The truncation policy is part of the key: changing its constants or its code
# re-embeds, so the head is never trained on inputs the server doesn't produce.
POLICY = hashlib.sha256(
    "|".join(
        (
            c.MODEL_REVISION,
            c.PREFIX,
            str(c.MAX_TOKENS),
            str(c.HEAD_TOKENS),
            str(c.MAX_CHARS),
            inspect.getsource(c.prepare),
            inspect.getsource(c.Embedder.ids),
        )
    ).encode()
).hexdigest()


def text_key(text: str) -> str:
    return hashlib.sha256(f"{POLICY}\0{text}".encode()).hexdigest()


def embed_cached(embed, texts: list[str], cache_dir: Path = EMB_CACHE, batch: int = 16) -> np.ndarray:
    """embed(list[str]) -> (n, DIM), with one .npy file per text under
    cache_dir. Long and short texts are batched separately to waste little on
    padding."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = np.zeros((len(texts), c.DIM), dtype=np.float32)
    todo = []
    for i, t in enumerate(texts):
        f = cache_dir / f"{text_key(t)}.npy"
        if f.exists():
            out[i] = np.load(f)
        else:
            todo.append(i)
    todo.sort(key=lambda i: len(texts[i]))
    for n, start in enumerate(range(0, len(todo), batch)):
        idx = todo[start : start + batch]
        vecs = embed([texts[i] for i in idx])
        for i, v in zip(idx, vecs, strict=True):
            out[i] = v
            np.save(cache_dir / f"{text_key(texts[i])}.npy", v.astype(np.float32))
        if n % 10 == 0:
            print(f"embed: {start + len(idx)}/{len(todo)} new", file=sys.stderr, flush=True)
    return out


# ---- the head -----------------------------------------------------------------------


def fit(x: np.ndarray, y: np.ndarray, l2: float, steps: int = 1500, lr: float = 0.05, seed: int = 7) -> c.Head:
    """Multinomial logistic regression with class-balanced weights and L2,
    fitted with Adam on standardised features. The standardisation is folded
    into the weights, so serving is softmax(Wx + b) on the raw embedding."""
    k = len(c.TIERS)
    mean, std = x.mean(axis=0), x.std(axis=0) + 1e-6
    z = (x - mean) / std
    n, d = z.shape
    counts = np.bincount(y, minlength=k).astype(np.float64)
    cw = np.where(counts > 0, n / (k * np.maximum(counts, 1)), 0.0)
    sw = cw[y] / cw[y].sum()
    onehot = np.eye(k)[y]
    rng = np.random.default_rng(seed)
    w, b = rng.normal(0, 0.01, (k, d)), np.zeros(k)
    mw, vw, mb, vb = np.zeros_like(w), np.zeros_like(w), np.zeros_like(b), np.zeros_like(b)
    for t in range(1, steps + 1):
        p = c.softmax(z @ w.T + b)
        g = (p - onehot) * sw[:, None]
        gw, gb = g.T @ z + l2 * w, g.sum(axis=0)
        mw, vw = 0.9 * mw + 0.1 * gw, 0.999 * vw + 0.001 * gw**2
        mb, vb = 0.9 * mb + 0.1 * gb, 0.999 * vb + 0.001 * gb**2
        corr = np.sqrt(1 - 0.999**t) / (1 - 0.9**t)
        w -= lr * corr * mw / (np.sqrt(vw) + 1e-8)
        b -= lr * corr * mb / (np.sqrt(vb) + 1e-8)
    # A Tier missing from the training data can never be predicted.
    b = np.where(counts > 0, b, -1e4)
    w_raw = w / std
    return c.Head(w_raw.astype(np.float32), (b - w_raw @ mean).astype(np.float32), {"l2": l2})


def report(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    k = len(c.TIERS)
    cm = np.zeros((k, k), dtype=int)
    for t, p in zip(y_true, y_pred, strict=True):
        cm[t, p] += 1
    per_tier, f1s = {}, []
    for i, tier in enumerate(c.TIERS):
        support = int(cm[i].sum())
        if support == 0 and cm[:, i].sum() == 0:
            continue
        recall = cm[i, i] / support if support else 0.0
        precision = cm[i, i] / cm[:, i].sum() if cm[:, i].sum() else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1s.append(f1)
        per_tier[tier] = {"support": support, "accuracy": round(recall, 4), "precision": round(precision, 4), "f1": round(f1, 4)}
    return {
        "n": int(len(y_true)),
        "accuracy": round(float((y_true == y_pred).mean()) if len(y_true) else 0.0, 4),
        "macro_f1": round(float(np.mean(f1s)) if f1s else 0.0, 4),
        "per_tier": per_tier,
        "confusion": {"rows_true_cols_predicted": list(c.TIERS), "matrix": cm.tolist()},
    }


def by_form(rows: list[dict], y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Eval accuracy per prompt form. Rounds 1 and 2 (bare, snippet, error,
    followup) stay comparable across retrains; conversation and pasted are round 3."""
    forms = np.asarray([r.get("form", "") for r in rows])
    return {
        f: {"n": int((forms == f).sum()), "accuracy": round(float((y_true[forms == f] == y_pred[forms == f]).mean()), 4)}
        for f in sorted(set(forms))
    }


def choose(xtr, ytr, xval, yval, grid=L2_GRID) -> tuple[c.Head, dict]:
    """Fits one head per L2 strength and keeps the best on val (macro-F1). With
    no val rows, the middle of the grid."""
    if len(yval) == 0:
        l2 = grid[len(grid) // 2]
        return fit(xtr, ytr, l2), {"l2": l2, "val": None}
    scores = {}
    best = None
    for l2 in grid:
        h = fit(xtr, ytr, l2)
        r = report(yval, h.probs(xval).argmax(axis=1))
        scores[str(l2)] = r["macro_f1"]
        if best is None or r["macro_f1"] > best[1]["macro_f1"]:
            best = (h, r, l2)
    return best[0], {"l2": best[2], "val": best[1], "val_macro_f1_by_l2": scores}


# ---- latency -----------------------------------------------------------------------


def latency(classify, texts: list[str], warmup: int = 5) -> dict:
    """Per-request latency of classify(text), one at a time (batch size 1)."""
    for t in texts[:warmup]:
        classify(t)
    ms = []
    for t in texts:
        t0 = time.perf_counter()
        classify(t)
        ms.append((time.perf_counter() - t0) * 1000)
    a = np.asarray(ms)
    return {"n": len(ms), "p50_ms": round(float(np.percentile(a, 50)), 1), "p95_ms": round(float(np.percentile(a, 95)), 1),
            "max_ms": round(float(a.max()), 1)}  # fmt: skip


def machine() -> dict:
    info = {"platform": platform.platform(), "machine": platform.machine(), "cpus": os.cpu_count()}
    try:
        import subprocess

        info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    return info


# ---- main --------------------------------------------------------------------------


def train(rows: list[dict], embed, classify=None, latency_texts: list[str] | None = None, cache_dir: Path = EMB_CACHE) -> tuple:
    idx = {t: i for i, t in enumerate(c.TIERS)}
    parts = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "eval")}
    if len({r["tier"] for r in parts["train"]}) < 2:
        sys.exit(f"train: need at least two Tiers in the train split, have {sorted({r['tier'] for r in parts['train']})}")
    xs = {s: embed_cached(embed, [r["text"] for r in p], cache_dir) for s, p in parts.items()}
    ys = {s: np.asarray([idx[r["tier"]] for r in p], dtype=int) for s, p in parts.items()}
    head, chosen = choose(xs["train"], ys["train"], xs["val"], ys["val"])
    metrics = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": {s: {t: sum(r["tier"] == t for r in p) for t in c.TIERS} for s, p in parts.items()},
        "l2": chosen["l2"],
        "val": chosen["val"],
        "val_macro_f1_by_l2": chosen.get("val_macro_f1_by_l2"),
        "eval": report(ys["eval"], head.probs(xs["eval"]).argmax(axis=1)) if len(ys["eval"]) else None,
    }
    if len(ys["eval"]):
        metrics["eval_by_form"] = by_form(parts["eval"], ys["eval"], head.probs(xs["eval"]).argmax(axis=1))
    if classify and latency_texts:
        metrics["latency"] = latency(lambda t: classify(head, t), latency_texts)
        metrics["latency"]["machine"] = machine()
    return head, metrics


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-generated", action="store_true", help="provisional smoke run on dataset/generated-raw.jsonl")
    ap.add_argument("--threads", type=int, default=int(os.environ.get("ROUTER_THREADS", "2")),
                    help="ONNX Runtime threads for the latency run (the server's ROUTER_THREADS)")  # fmt: skip
    ap.add_argument("--latency-samples", type=int, default=200)
    a = ap.parse_args(argv)

    provisional = a.from_generated
    rows = load_generated() if provisional else load_prompts()
    if not rows:
        sys.exit("train: no rows; run the dataset split (and apply-review) first, or pass --from-generated")
    model_dir = c.fetch(c.CACHE / "model")
    batch_embedder = c.Embedder(model_dir)
    serve_embedder = c.Embedder(model_dir, threads=a.threads)

    def classify(head: c.Head, text: str) -> np.ndarray:
        return head.probs(serve_embedder.embed([text]))[0]

    evals = [r["text"] for r in rows if r["split"] == "eval"]
    random.Random(7).shuffle(evals)
    # Plus the worst case: an input that fills all MAX_TOKENS.
    lat_texts = evals[: a.latency_samples] + ["def f(x):\n    return x * 2\n" * 200] * 10
    head, metrics = train(rows, batch_embedder.embed, classify, lat_texts)
    metrics["latency"]["threads"] = a.threads
    metrics["provisional"] = provisional
    metrics["source"] = "dataset/generated-raw.jsonl (generated Tier as label)" if provisional else "dataset/prompts.jsonl"
    metrics["targets"] = {"accuracy": TARGET_ACCURACY, "p95_ms": TARGET_P95_MS, "on": "c7i.xlarge (task 2.2)"}
    head.meta.update(provisional=provisional, trained_at=metrics["trained_at"], rows=metrics["rows"], prefix=c.PREFIX)
    suffix = ".provisional" if provisional else ""
    head_path, metrics_path = c.HEAD.with_name(f"head{suffix}.json"), c.HEAD.with_name(f"metrics{suffix}.json")
    head.save(head_path)
    metrics_path.write_text(json.dumps(metrics, indent=1) + "\n")
    e = metrics["eval"] or {}
    print(f"train: eval accuracy {e.get('accuracy')}, macro-F1 {e.get('macro_f1')} on {e.get('n')} prompts; "
          f"latency p50 {metrics['latency']['p50_ms']} ms, p95 {metrics['latency']['p95_ms']} ms with {a.threads} threads "
          f"on {metrics['latency']['machine'].get('cpu') or platform.machine()}")  # fmt: skip
    print(f"train: wrote {head_path.relative_to(ROOT)} and {metrics_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

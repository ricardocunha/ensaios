"""Milestone 4 evaluation: how sure are the Milestone 2 differences?

    uv run python -m eye_rag.m4      # -> runs/m4_eval.json

Paired bootstrap over test images (the 609 deduplicated ones every arm answered):
each resample draws images with replacement and re-scores every arm on the same draw,
so a difference's interval accounts for the arms sharing images. Macro-F1 in a resample
averages over the frequent conditions that have at least one positive in it (a condition
with no positives would otherwise score F1 = 1). Rates over citations resample images,
not citations, so the several citations of one image move together.

Reads only run files; no model is called.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from eye_rag.metrics import f1_per_label

RUNS = Path("runs")
B = 2000
SEED = 0


def macro_f1_present(y: np.ndarray, p: np.ndarray, columns: Sequence[int]) -> float:
    cols = [j for j in columns if y[:, j].any()]
    return float(f1_per_label(y[:, cols], p[:, cols]).mean())


def bootstrap(n: int, stat: Callable[[np.ndarray], float], b: int = B, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.array([stat(rng.integers(0, n, n)) for _ in range(b)])


def interval(point: float, draws: np.ndarray) -> dict:
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"point": round(point, 4), "ci95": [round(float(lo), 4), round(float(hi), 4)]}


def ratio_stat(num: np.ndarray, den: np.ndarray) -> Callable[[np.ndarray], float]:
    """Pooled rate sum(num)/sum(den) over the resampled images."""
    return lambda i: float(num[i].sum() / max(den[i].sum(), 1))


def evaluate(out_dir: Path = RUNS, split: str = "test", b: int = B) -> dict:
    from eye_rag.evaluate import compute
    from eye_rag.explain import _rows
    from eye_rag.m2 import vlm_matrix

    c = compute()
    recs, frequent = c["recs"][split], c["frequent"]
    pos = {r.id: i for i, r in enumerate(recs)}
    truth = {r.id: set(r.labels) for r in recs}
    rows = {a: {r["id"]: r for r in _rows(out_dir / f"m2_vlm_{split}_{a}.jsonl")} for a in ("zero_shot", "retrieval", "shuffled")}
    ids = sorted(set.intersection(*(set(v) for v in rows.values())), key=lambda x: int(x.split("/")[1]))
    idx = np.array([pos[i] for i in ids])
    y = c["y"][split][idx]
    knn = next(m for m in c["methods"] if m.startswith("knn_weighted"))
    P = {"knn_weighted": c["methods"][knn][idx], **{f"vlm_{a}": vlm_matrix([rows[a][i] for i in ids])[1] for a in rows}}
    n = len(ids)

    out: dict = {"split": split, "n_images": n, "resamples": b, "seed": SEED, "macro_f1_frequent": {}, "f1_disease_risk": {}, "differences": {}}
    for a, p in P.items():
        out["macro_f1_frequent"][a] = interval(macro_f1_present(y, p, frequent), bootstrap(n, lambda i, p=p: macro_f1_present(y[i], p[i], frequent), b))
        out["f1_disease_risk"][a] = interval(float(f1_per_label(y[:, :1], p[:, :1])[0]), bootstrap(n, lambda i, p=p: float(f1_per_label(y[i, :1], p[i, :1])[0]), b))
    for x, z in (("vlm_retrieval", "knn_weighted"), ("vlm_retrieval", "vlm_zero_shot"), ("vlm_retrieval", "vlm_shuffled"), ("vlm_shuffled", "vlm_zero_shot")):
        def d(i, x=x, z=z):
            return macro_f1_present(y[i], P[x][i], frequent) - macro_f1_present(y[i], P[z][i], frequent)
        out["differences"][f"{x} - {z}"] = interval(d(np.arange(n)), bootstrap(n, d, b))

    # faithfulness: answer changed when only the case labels changed
    changed = np.array([set(rows["retrieval"][i]["labels"]) != set(rows["shuffled"][i]["labels"]) for i in ids], dtype=float)
    out["answer_changed"] = interval(float(changed.mean()), bootstrap(n, lambda i: float(changed[i].mean()), b))

    # explanations: verification rate, and how often a verified case citation names a true label
    ex = {a: {r["id"]: r for r in _rows(out_dir / f"m2_explain_{split}_{a}.jsonl")} for a in ("retrieval", "shuffled")}
    out["explanations"] = {}
    for a, by in ex.items():
        if not by:
            continue
        verified = np.array([bool(by.get(i, {}).get("verified")) for i in ids], dtype=float)
        has = np.array([i in by for i in ids], dtype=float)
        cites = [[f for f in (by[i]["findings"] or []) if f["source"] != "image"] if i in by and by[i]["verified"] else [] for i in ids]
        den = np.array([len(cs) for cs in cites], dtype=float)
        num = np.array([sum(f["label"] in (truth[i] or {"normal"}) for f in cs) for i, cs in zip(ids, cites)], dtype=float)
        out["explanations"][a] = {
            "verified": interval(float(verified.sum() / has.sum()), bootstrap(n, ratio_stat(verified, has), b)),
            "verified_case_citations": int(den.sum()),
            "verified_case_citation_label_true": interval(float(num.sum() / den.sum()), bootstrap(n, ratio_stat(num, den), b)),
        }
    (out_dir / "m4_eval.json").write_text(json.dumps(out, indent=1))
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=RUNS)
    p.add_argument("--resamples", type=int, default=B)
    a = p.parse_args(argv)
    print(json.dumps(evaluate(a.out, b=a.resamples), indent=1))
    print("done", file=sys.stderr)


if __name__ == "__main__":
    main()

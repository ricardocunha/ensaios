"""Run the VLM arms on the deduplicated split and append one JSON line per image.

    uv run --group vlm python -m eye_rag.diagnose --arm zero_shot --split test [--n 300]
    uv run --group vlm python -m eye_rag.diagnose --arm retrieval --split test --retrieval dense
    uv run --group vlm python -m eye_rag.diagnose --arm shuffled --split test --retrieval hybrid_knn

Images: the split minus docs/exclusions.json, in a seeded order, first `--n`. Resumable.
Retrieved cases come from the training split only. The `shuffled` arm is the
faithfulness test: the retrieval arm's case images with wrong recorded findings
(see `shuffled_case_labels`).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

from eye_rag.dedup import load_exclusions
from eye_rag.vlm import Case, MlxVlm, VisionModel, diagnose

SEED = 0
K_CASES = 3


def subset(ids: list[str], excluded: frozenset[str], n: int | None, seed: int = SEED) -> list[str]:
    """Deduplicated ids in a seeded random order, truncated to n."""
    keep = [i for i in ids if i not in excluded]
    random.Random(seed).shuffle(keep)
    return keep if n is None else keep[:n]


def shuffled_case_labels(qid: str, true: list[tuple[str, ...]], pool: list[tuple[str, ...]], seed: int = SEED) -> list[tuple[str, ...]]:
    """Wrong findings for each retrieved case: drawn from the training label sets (so their
    frequencies are realistic), never equal to any of this query's true case labels.
    Seeded per query, so a resumed run shows the same labels."""
    rng = random.Random(f"{seed}:{qid}")
    real = set(true)
    out = []
    for _ in true:
        for _try in range(1000):
            cand = rng.choice(pool)
            if cand not in real:
                break
        else:
            raise ValueError(f"no label set outside {real}")
        out.append(cand)
    return out


def retrieved_cases(split: str, method: str, k: int) -> dict[str, list[int]]:
    """{query id: training-record indices of its top-k cases} for dense or hybrid_knn retrieval."""
    from eye_rag.evaluate import compute
    from eye_rag.hybrid import build_hybrid_index, query_text_from_labels, search
    from eye_rag.index import QDRANT_PATH, open_client
    from eye_rag.m2 import knn_prelabels

    c = compute()
    client = open_client(QDRANT_PATH)
    vocab = build_hybrid_index(client, c["recs"]["train"], c["vec"]["train"])
    texts = None if method == "dense" else [query_text_from_labels(x) for x in knn_prelabels(c, split)]
    nb = search(client, vocab, c["vec"][split], texts, k)
    client.close()
    return {r.id: [int(x) for x in nb[i]] for i, r in enumerate(c["recs"][split])}


def run(model: VisionModel, arm: str, split: str, n: int | None, retrieval: str, out_dir: Path, k: int = K_CASES) -> Path:
    from eye_rag.rfmid import load_split

    recs = {r.id: r for r in load_split(split)}
    train = load_split("train")
    ids = subset(list(recs), load_exclusions().get(split, frozenset()), n)
    out = out_dir / f"m2_vlm_{split}_{arm}.jsonl"
    done = {json.loads(x)["id"] for x in out.read_text().splitlines() if x.strip()} if out.exists() else set()
    with_cases = arm in ("retrieval", "shuffled")
    cases_by_id = retrieved_cases(split, retrieval, k) if with_cases else {}
    pool = [tuple(sorted(r.label_set)) for r in train]
    (out_dir / f"m2_vlm_{split}_{arm}.meta.json").write_text(json.dumps({
        "model": model.name, "arm": arm, "split": split, "n_requested": n, "n_in_subset": len(ids),
        "seed": SEED, "subset": "deduplicated split, shuffled with random.Random(seed), first n",
        "retrieval": retrieval if with_cases else None, "k_cases": k if with_cases else 0,
        "case_labels": "random other training label sets (shuffled_case_labels)" if arm == "shuffled" else "recorded",
    }, indent=1))
    todo = [i for i in ids if i not in done]
    print(f"{arm}/{split}: {len(ids)} in subset, {len(done)} done, {len(todo)} to run", file=sys.stderr)
    t0 = time.perf_counter()
    with out.open("a") as f:
        for j, qid in enumerate(todo, 1):
            nb = cases_by_id.get(qid, [])
            true = [tuple(sorted(train[x].label_set)) for x in nb]
            shown = shuffled_case_labels(qid, true, pool) if arm == "shuffled" else true
            cases = [Case(train[x].path, labs) for x, labs in zip(nb, shown)]
            o = diagnose(model, recs[qid].path, cases)
            row = {
                "id": qid,
                "labels": o.diagnosis.labels if o.diagnosis else None,
                "cited_cases": o.diagnosis.cited_cases if o.diagnosis else None,
                "rationale": o.diagnosis.rationale if o.diagnosis else None,
                "attempts": o.attempts,
                "errors": o.errors,
                "seconds": round(o.seconds, 2),
                "case_ids": [train[x].id for x in cases_by_id.get(qid, [])],
                "case_labels": [list(c.labels) for c in cases],
                **({"true_case_labels": [list(t) for t in true]} if arm == "shuffled" else {}),
                "raw_last": o.raw[-1][:1000],
            }
            f.write(json.dumps(row) + "\n")
            f.flush()
            if j % 10 == 0 or j == len(todo):
                el = time.perf_counter() - t0
                print(f"  {j}/{len(todo)}  {el / j:.1f}s/img  eta {el / j * (len(todo) - j) / 60:.0f} min", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", choices=["zero_shot", "retrieval", "shuffled"], required=True)
    p.add_argument("--split", default="test", choices=["val", "test"])
    p.add_argument("--n", type=int, default=None)
    p.add_argument("--retrieval", choices=["dense", "hybrid_knn"], default="dense")
    p.add_argument("--out", type=Path, default=Path("runs"))
    a = p.parse_args(argv)
    np.random.seed(SEED)
    a.out.mkdir(parents=True, exist_ok=True)
    run(MlxVlm(), a.arm, a.split, a.n, a.retrieval, a.out)


if __name__ == "__main__":
    main()

"""Milestone 2 evaluation.

    uv run python -m eye_rag.m2 baselines    # M1 baselines re-scored: all vs deduplicated test
    uv run python -m eye_rag.m2 retrieval    # label precision@k: dense vs hybrid (Qdrant RRF)
    uv run python -m eye_rag.m2 score        # three-arm table from the VLM runs (eye_rag.diagnose)

Everything reads the exclusion list in docs/exclusions.json (see eye_rag.dedup).
Choices are made on validation (deduplicated); the test split is only scored.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from eye_rag import baselines as B
from eye_rag.dedup import load_exclusions
from eye_rag.labels import CODES, DISEASE_RISK, NORMAL
from eye_rag.metrics import any_overlap_precision_at_k, f1_per_label, label_precision_at_k, macro_f1

COLUMNS = (DISEASE_RISK, *CODES)
P_AT = (1, 3, 5, 10)
RUNS = Path("runs")


def _metrics(y: np.ndarray, p: np.ndarray, frequent: Sequence[int], present: Sequence[int]) -> dict:
    f = f1_per_label(y, p)
    return {
        "n": int(len(y)),
        "macro_f1_frequent": round(macro_f1(y, p, frequent), 4),
        "macro_f1_present": round(macro_f1(y, p, present), 4),
        "f1_disease_risk": round(float(f[0]), 4),
    }


def knn_prelabels(c: dict, split: str) -> list[list[str]]:
    """kNN pre-labels per image (condition codes, or [NORMAL]), using the M1 choice (k, t)."""
    k, t = c["choice"].k, c["choice"].threshold
    pred = B.knn_scores(c["y_nb"][split], c["sims"][split], k) >= t
    out = []
    for row in pred:
        labs = [COLUMNS[j] for j in range(1, len(COLUMNS)) if row[j]]
        out.append(labs if labs else [NORMAL])
    return out


# --------------------------------------------------------------------------- 1. baselines all vs dedup


def baselines(out_dir: Path = RUNS) -> dict:
    from eye_rag.evaluate import compute

    c = compute()
    excl = load_exclusions()
    recs, y, frequent = c["recs"], c["y"], c["frequent"]
    test_ids = [r.id for r in recs["test"]]
    keep = np.array([i not in excl["test"] for i in test_ids])
    yt = y["test"]

    def present(mask):
        return [j for j in range(1, len(COLUMNS)) if yt[mask, j].sum() > 0]

    pres_all, pres_dd = present(np.ones(len(yt), bool)), present(keep)
    summary = {}
    for m, p in c["methods"].items():
        summary[m] = {
            "all": _metrics(yt, p, frequent, pres_all),
            "dedup": _metrics(yt[keep], p[keep], frequent, pres_dd),
            "excluded_only": _metrics(yt[~keep], p[~keep], frequent, present(~keep)),
        }

    # kNN re-tuned on deduplicated validation (choices must not lean on val/train duplicates either)
    vkeep = np.array([r.id not in excl["val"] for r in recs["val"]])
    ch = B.tune_knn(y["val"][vkeep], c["y_nb"]["val"][vkeep], c["sims"]["val"][vkeep], frequent)
    p = B.knn_scores(c["y_nb"]["test"], c["sims"]["test"], ch.k) >= ch.threshold
    retuned = {"choice": ch.__dict__, "dedup": _metrics(yt[keep], p[keep], frequent, pres_dd), "all": _metrics(yt, p, frequent, pres_all)}

    # per condition, kNN weighted: all vs dedup
    knn_name = next(m for m in c["methods"] if m.startswith("knn_weighted"))
    pk = c["methods"][knn_name]
    f_all, f_dd = f1_per_label(yt, pk), f1_per_label(yt[keep], pk[keep])
    per_cond = {
        COLUMNS[j]: {"test_all": int(yt[:, j].sum()), "test_dedup": int(yt[keep, j].sum()), "f1_all": round(float(f_all[j]), 4), "f1_dedup": round(float(f_dd[j]), 4)}
        for j in [0, *frequent]
    }

    # retrieval quality all vs dedup
    train_sets = [r.label_set for r in recs["train"]]
    test_sets = [r.label_set for r in recs["test"]]
    nb_sets = [[train_sets[i] for i in row] for row in c["nb"]["test"][0]]
    retr = {}
    for name, mask in (("all", np.ones(len(yt), bool)), ("dedup", keep)):
        idx = np.flatnonzero(mask)
        retr[name] = {
            "any_overlap": {k: round(any_overlap_precision_at_k([test_sets[i] for i in idx], [nb_sets[i] for i in idx], k), 4) for k in (1, 5, 10)},
            "frequent_macro": {k: round(float(np.nanmean(label_precision_at_k(yt[idx], c["y_nb"]["test"][idx], k)[frequent])), 4) for k in (1, 5, 10)},
        }

    # how often is an excluded test image's top-1 neighbour its own duplicate?
    pairs = json.loads((out_dir / "dedup_pairs.json").read_text())["pairs"]
    partner: dict[str, set[str]] = {}
    for pr in pairs:
        partner.setdefault(pr["a"], set()).add(pr["b"])
        partner.setdefault(pr["b"], set()).add(pr["a"])
    train_ids = [r.id for r in recs["train"]]
    excl_test = [i for i, t in enumerate(test_ids) if not keep[i]]
    with_train_partner = [i for i in excl_test if any(x.startswith("train/") for x in partner.get(test_ids[i], ()))]
    top1_is_dup = sum(train_ids[c["nb"]["test"][0][i, 0]] in partner.get(test_ids[i], ()) for i in with_train_partner)
    top1_dup_same_labels = sum(
        train_ids[c["nb"]["test"][0][i, 0]] in partner.get(test_ids[i], ())
        and recs["train"][c["nb"]["test"][0][i, 0]].label_set == recs["test"][i].label_set
        for i in with_train_partner
    )

    result = {
        "excluded": {s: len(v) for s, v in excl.items()},
        "test_sizes": {"all": int(len(yt)), "dedup": int(keep.sum())},
        "frequent_conditions": [COLUMNS[j] for j in frequent],
        "conditions_present": {"all": len(pres_all), "dedup": len(pres_dd)},
        "summary": summary,
        "knn_retuned_on_dedup_val": retuned,
        "knn_per_condition": per_cond,
        "retrieval": retr,
        "excluded_test_with_train_partner": len(with_train_partner),
        "top1_neighbour_is_the_duplicate": int(top1_is_dup),
        "top1_duplicate_with_identical_labels": int(top1_dup_same_labels),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "m2_baselines_dedup.json").write_text(json.dumps(result, indent=1))
    return result


# --------------------------------------------------------------------------- 2. retrieval dense vs hybrid


def retrieval(out_dir: Path = RUNS, vlm_labels: dict[str, list[str]] | None = None) -> dict:
    """Label precision@k of dense-only vs hybrid (dense + sparse report text, RRF), on the
    deduplicated validation and test splits (and all of test)."""
    from eye_rag.evaluate import compute
    from eye_rag.hybrid import build_hybrid_index, query_text_from_labels, search
    from eye_rag.index import QDRANT_PATH, open_client

    c = compute()
    excl = load_exclusions()
    recs, y, vec, frequent = c["recs"], c["y"], c["vec"], c["frequent"]
    client = open_client(QDRANT_PATH)
    vocab = build_hybrid_index(client, recs["train"], vec["train"])
    train_sets = [r.label_set for r in recs["train"]]
    kmax = max(P_AT)

    out: dict = {"query_text_sources": {
        "dense": "no text: image vector only",
        "hybrid_knn": "report built from the kNN pre-labels (M1 choice k, t) of the query image",
        "hybrid_vlm": "report built from the labels the VLM predicted zero-shot (arm a), when available",
        "hybrid_oracle": "report built from the query's TRUE labels: uses test labels, an upper bound only",
    }}
    for split in ("val", "test"):
        ids = [r.id for r in recs[split]]
        keep = np.array([i not in excl.get(split, frozenset()) for i in ids])
        sources: dict[str, list[str] | None] = {
            "dense": None,
            "hybrid_knn": [query_text_from_labels(x) for x in knn_prelabels(c, split)],
            "hybrid_oracle": [query_text_from_labels(sorted(r.label_set)) for r in recs[split]],
        }
        if vlm_labels and split == "test":
            have = np.array([i in vlm_labels for i in ids])
            if have.any():
                sources["hybrid_vlm"] = [query_text_from_labels([NORMAL] if vlm_labels.get(i) == ["normal"] else vlm_labels.get(i, [])) for i in ids]
        res = {}
        for name, texts in sources.items():
            nb = search(client, vocab, vec[split], texts, kmax)
            y_nb = y["train"][nb]
            nb_sets = [[train_sets[i] for i in row] for row in nb]
            masks = {"dedup": keep} if split == "val" else {"all": np.ones(len(ids), bool), "dedup": keep}
            if name == "hybrid_vlm":
                masks = {"vlm_subset_dedup": keep & have}
            res[name] = {}
            for mname, m in masks.items():
                idx = np.flatnonzero(m)
                res[name][mname] = {
                    "n": int(len(idx)),
                    "frequent_macro_p": {k: round(float(np.nanmean(label_precision_at_k(y[split][idx], y_nb[idx], k)[frequent])), 4) for k in P_AT},
                    "any_overlap_p": {k: round(any_overlap_precision_at_k([recs[split][i].label_set for i in idx], [nb_sets[i] for i in idx], k), 4) for k in P_AT},
                }
            if name == "hybrid_vlm" and "dense" in res:  # dense on the same subset, for a fair comparison
                idx = np.flatnonzero(keep & have)
                nb_d = search(client, vocab, vec[split][idx], None, kmax)
                res["dense"]["vlm_subset_dedup"] = {
                    "n": int(len(idx)),
                    "frequent_macro_p": {k: round(float(np.nanmean(label_precision_at_k(y[split][idx], y["train"][nb_d], k)[frequent])), 4) for k in P_AT},
                    "any_overlap_p": {k: round(any_overlap_precision_at_k([recs[split][i].label_set for i in idx], [[train_sets[j] for j in row] for row in nb_d], k), 4) for k in P_AT},
                }
        out[split] = res
    client.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "m2_retrieval.json").write_text(json.dumps(out, indent=1))
    return out


# --------------------------------------------------------------------------- 3. three-arm score


def vlm_matrix(rows: Sequence[dict]) -> tuple[list[str], np.ndarray, int]:
    """(ids, (n, len(COLUMNS)) predictions, number of failed answers) from diagnose rows.
    A failed answer (no valid JSON after retries) predicts nothing, i.e. counts as normal."""
    ids, P, failed = [], np.zeros((len(rows), len(COLUMNS)), dtype=bool), 0
    for i, r in enumerate(rows):
        ids.append(r["id"])
        labs = r.get("labels")
        if labs is None:
            failed += 1
            continue
        for lab in labs:
            if lab in CODES:
                P[i, COLUMNS.index(lab)] = True
        P[i, 0] = labs != ["normal"]
    return ids, P, failed


def read_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def score(out_dir: Path = RUNS, split: str = "test") -> dict:
    from eye_rag.evaluate import compute

    c = compute()
    recs, y, frequent = c["recs"], c["y"], c["frequent"]
    pos = {r.id: i for i, r in enumerate(recs[split])}
    knn_name = next(m for m in c["methods"] if m.startswith("knn_weighted"))
    arms = {"vlm_zero_shot": read_rows(out_dir / f"m2_vlm_{split}_zero_shot.jsonl"), "vlm_retrieval": read_rows(out_dir / f"m2_vlm_{split}_retrieval.jsonl")}
    done = [set(r["id"] for r in rows) for rows in arms.values() if rows]
    common = sorted(set.intersection(*done), key=lambda x: int(x.split("/")[1])) if done else []
    if not common:
        raise SystemExit("no VLM rows yet: run eye_rag.diagnose first")
    idx = np.array([pos[i] for i in common])
    yt = y[split][idx]
    present = [j for j in range(1, len(COLUMNS)) if yt[:, j].sum() > 0]
    preds, meta = {}, {}
    for arm, rows in arms.items():
        by = {r["id"]: r for r in rows}
        ids, P, failed = vlm_matrix([by[i] for i in common])
        preds[arm] = P
        sel = [by[i] for i in common]
        meta[arm] = {
            "failed": failed,
            "retried": sum(r["attempts"] > 1 for r in sel),
            "mean_seconds": round(float(np.mean([r["seconds"] for r in sel])), 2),
            "total_seconds": round(float(np.sum([r["seconds"] for r in sel])), 1),
            "mean_labels": round(float(np.mean([len(r["labels"] or []) for r in sel])), 2),
        }
    preds["knn_weighted"] = c["methods"][knn_name][idx] if split == "test" else None
    summary = {a: _metrics(yt, p, frequent, present) for a, p in preds.items()}
    f = {a: f1_per_label(yt, p) for a, p in preds.items()}
    per_cond = {COLUMNS[j]: {"n_pos": int(yt[:, j].sum()), **{a: round(float(f[a][j]), 4) for a in preds}} for j in [0, *frequent]}
    # cited cases and agreement with retrieved labels
    rows_b = {r["id"]: r for r in arms["vlm_retrieval"]}
    copy = [set(rows_b[i]["labels"] or []) <= set(lab for case in rows_b[i]["case_labels"] for lab in case) | {"normal"} for i in common if "case_labels" in rows_b[i]]
    result = {
        "split": split,
        "n_images": len(common),
        "subset_note": json.loads((out_dir / f"m2_vlm_{split}_retrieval.meta.json").read_text()) if (out_dir / f"m2_vlm_{split}_retrieval.meta.json").exists() else None,
        "summary": summary,
        "per_condition": per_cond,
        "vlm_runs": meta,
        "retrieval_arm_labels_all_seen_in_cases": round(float(np.mean(copy)), 4) if copy else None,
        "knn_choice": c["choice"].__dict__,
    }
    (out_dir / f"m2_three_arms_{split}.json").write_text(json.dumps(result, indent=1))
    return result


def three_arm_markdown(r: dict) -> str:
    arms = list(r["summary"])
    out = [f"{r['n_images']} images ({r['split']}, deduplicated)", "", "| Arm | macro-F1, 16 frequent | macro-F1, present | F1 Disease_Risk |", "|---|---|---|---|"]
    for a in arms:
        s = r["summary"][a]
        out.append(f"| {a} | {s['macro_f1_frequent']:.3f} | {s['macro_f1_present']:.3f} | {s['f1_disease_risk']:.3f} |")
    out += ["", "| Condition | positives | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
    for c, v in r["per_condition"].items():
        out.append(f"| {c} | {v['n_pos']} | " + " | ".join(f"{v[a]:.2f}" for a in arms) + " |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["baselines", "retrieval", "score"])
    p.add_argument("--out", type=Path, default=RUNS)
    p.add_argument("--with-vlm", action="store_true", help="retrieval: add the hybrid query from VLM zero-shot labels")
    a = p.parse_args(argv)
    if a.command == "baselines":
        r = baselines(a.out)
    elif a.command == "retrieval":
        vl = None
        if a.with_vlm:
            vl = {x["id"]: x["labels"] for x in read_rows(a.out / "m2_vlm_test_zero_shot.jsonl") if x.get("labels")}
        r = retrieval(a.out, vl)
    else:
        r = score(a.out)
        (a.out / "m2_three_arms_test.md").write_text(three_arm_markdown(r))
        print(three_arm_markdown(r))
    print(json.dumps(r, indent=1))
    print("done", file=sys.stderr)


if __name__ == "__main__":
    main()

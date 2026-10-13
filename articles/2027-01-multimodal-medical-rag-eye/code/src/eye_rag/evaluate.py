"""Milestone 1: build the index and measure the two baselines on the RFMiD test split.

Index = the 1,920 training images. Choices (k, thresholds) are made on the validation
split; the test split is touched once, for the numbers.

    uv run python -m eye_rag.evaluate      # writes runs/m1_baselines.{json,md}
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

from eye_rag import baselines as B
from eye_rag.embed import TEMPLATES, BiomedCLIP, cached, image_embeddings
from eye_rag.index import (
    QDRANT_PATH,
    build_image_index,
    build_label_index,
    label_texts,
    open_client,
    search_images,
)
from eye_rag.labels import BY_CODE, CODES, DISEASE_RISK, NORMAL_DESCRIPTION
from eye_rag.metrics import any_overlap_precision_at_k, f1_per_label, label_precision_at_k, macro_f1
from eye_rag.rfmid import label_matrix

SEED = 0
FREQUENT_MIN_TRAIN = 20  # a condition is "frequent" with >= 20 training positives
MAX_K = 50
P_AT = (1, 5, 10)
COLUMNS = (DISEASE_RISK, *CODES)  # column 0 is Disease_Risk (abnormal vs normal)
ABNORMAL_TEXT = "an abnormal retina with signs of disease"


def _prompts() -> list[str]:
    """Templates x [Disease_Risk, 45 conditions], then templates x normal (the negative)."""
    classes = [ABNORMAL_TEXT] + [f"{BY_CODE[c].name}, {BY_CODE[c].description}" for c in CODES]
    return [t.format(c) for c in classes for t in TEMPLATES] + [t.format(NORMAL_DESCRIPTION) for t in TEMPLATES]


def compute(qdrant_path: Path = QDRANT_PATH) -> dict:
    """Everything the M1 baselines need, on every image of the official split: embeddings,
    labels, neighbours, the val-tuned choices and the test predictions per method.
    Milestone 2 reuses it to re-score on the deduplicated test split."""
    random.seed(SEED)
    np.random.seed(SEED)
    model = BiomedCLIP()

    t0 = time.perf_counter()
    data = {s: image_embeddings(s, model) for s in ("train", "val", "test")}
    recs = {s: r for s, (r, _) in data.items()}
    vec = {s: v for s, (_, v) in data.items()}
    y = {s: label_matrix(recs[s], COLUMNS) for s in recs}
    t_embed = time.perf_counter() - t0

    train_counts = y["train"].sum(0)
    frequent = [j for j in range(1, len(COLUMNS)) if train_counts[j] >= FREQUENT_MIN_TRAIN]

    def present(split: str) -> list[int]:
        return [j for j in range(1, len(COLUMNS)) if y[split][:, j].sum() > 0]

    # ---- index
    client = open_client(qdrant_path)
    build_image_index(client, recs["train"], vec["train"])
    rows = label_texts()
    label_vecs = cached("label_texts", [r[0] for r in rows], lambda: model.texts([r[3] for r in rows]))
    build_label_index(client, label_vecs)

    t1 = time.perf_counter()
    nb = {s: search_images(client, vec[s], MAX_K) for s in ("val", "test")}
    t_search = time.perf_counter() - t1
    y_nb = {s: y["train"][nb[s][0]] for s in nb}  # (n, MAX_K, L)
    sims = {s: nb[s][1] for s in nb}

    # ---- (a) kNN
    majority_test = B.knn_scores(y_nb["test"], sims["test"], k=5, weighted=False) >= 0.5
    choice = B.tune_knn(y["val"], y_nb["val"], sims["val"], frequent)
    knn_test = B.knn_scores(y_nb["test"], sims["test"], choice.k) >= choice.threshold

    # ---- (b) zero-shot
    texts = _prompts()
    tv = cached("zero_shot_prompts", texts, lambda: model.texts(texts))
    pv = B.prompt_vectors(tv, len(TEMPLATES))
    pos, neg = pv[:-1], pv[-1]
    zs = {s: B.zero_shot_probs(vec[s], pos, neg, model.logit_scale) for s in ("val", "test")}
    zs_test = zs["test"] >= 0.5
    thr = B.tune_thresholds_per_label(y["val"], zs["val"])
    zs_cal_test = zs["test"] >= thr

    # ---- reference: predict every label positive (an F1 floor)
    all_pos = np.ones_like(y["test"], dtype=bool)

    methods = {
        "all_positive": all_pos,
        "knn_majority_k5": majority_test,
        f"knn_weighted_k{choice.k}_t{choice.threshold}": knn_test,
        "zero_shot_p0.5": zs_test,
        "zero_shot_val_thresholds": zs_cal_test,
    }
    client.close()
    return {
        "model": model, "recs": recs, "vec": vec, "y": y, "frequent": frequent, "present": present,
        "train_counts": train_counts, "nb": nb, "y_nb": y_nb, "sims": sims, "choice": choice,
        "methods": methods, "zs": zs, "thr": thr, "t_embed": t_embed, "t_search": t_search,
    }


def run(out_dir: Path = Path("runs"), qdrant_path: Path = QDRANT_PATH) -> dict:
    c = compute(qdrant_path)
    model, recs, y, frequent, present = c["model"], c["recs"], c["y"], c["frequent"], c["present"]
    train_counts, nb, y_nb, choice, methods, thr = c["train_counts"], c["nb"], c["y_nb"], c["choice"], c["methods"], c["thr"]
    t_embed, t_search = c["t_embed"], c["t_search"]
    yt = y["test"]
    f1s = {m: f1_per_label(yt, p) for m, p in methods.items()}
    summary = {
        m: {
            "macro_f1_frequent": macro_f1(yt, p, frequent),
            "macro_f1_present_in_test": macro_f1(yt, p, present("test")),
            "f1_disease_risk": float(f1s[m][0]),
        }
        for m, p in methods.items()
    }

    # ---- retrieval quality
    train_sets = [r.label_set for r in recs["train"]]
    test_sets = [r.label_set for r in recs["test"]]
    nb_sets = [[train_sets[i] for i in row] for row in nb["test"][0]]
    p_any = {k: any_overlap_precision_at_k(test_sets, nb_sets, k) for k in P_AT}
    # expected value for a random draw from the index: share of training images sharing a label
    p_any_random = float(np.mean([np.mean([bool(q & t) for t in train_sets]) for q in test_sets]))
    p_label = {k: label_precision_at_k(yt, y_nb["test"], k) for k in P_AT}
    prevalence = y["train"].mean(0)

    result = {
        "dataset": "RFMiD 1.0 (HF mirror ctmedtech/RFMID, pinned revision)",
        "sizes": {s: len(recs[s]) for s in recs},
        "model": "BiomedCLIP-PubMedBERT_256-vit_base_patch16_224",
        "device": model.device,
        "seconds": {"embed_or_load_cache": round(t_embed, 1), "qdrant_search_val_test": round(t_search, 2)},
        "frequent_conditions": [COLUMNS[j] for j in frequent],
        "conditions_present_in_test": len(present("test")),
        "knn_choice": choice.__dict__,
        "summary": summary,
        "per_condition": {
            COLUMNS[j]: {
                "train": int(train_counts[j]),
                "test": int(yt[:, j].sum()),
                **{m: round(float(f1s[m][j]), 4) for m in methods},
                "p_at_10": None if np.isnan(p_label[10][j]) else round(float(p_label[10][j]), 4),
                "train_prevalence": round(float(prevalence[j]), 4),
            }
            for j in [0, *frequent]
        },
        "retrieval": {
            "any_overlap_p_at_k": {str(k): round(v, 4) for k, v in p_any.items()},
            "any_overlap_random_expectation": round(p_any_random, 4),
            "frequent_label_macro_p_at_k": {str(k): round(float(np.nanmean(p_label[k][frequent])), 4) for k in P_AT},
            "frequent_label_macro_prevalence": round(float(prevalence[frequent].mean()), 4),
        },
        "zero_shot_val_thresholds": {COLUMNS[j]: round(float(thr[j]), 4) for j in [0, *frequent]},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "m1_baselines.json").write_text(json.dumps(result, indent=2))
    (out_dir / "m1_baselines.md").write_text(to_markdown(result, list(methods)))
    return result


def to_markdown(r: dict, methods: list[str]) -> str:
    short = {m: m.replace("knn_", "kNN ").replace("zero_shot_", "ZS ") for m in methods}
    out = [f"Sizes: {r['sizes']} · device {r['device']} · knn choice {r['knn_choice']}", ""]
    out += ["| Method | macro-F1 (frequent) | macro-F1 (all present in test) | F1 Disease_Risk |", "|---|---|---|---|"]
    for m in methods:
        s = r["summary"][m]
        out.append(f"| {short[m]} | {s['macro_f1_frequent']:.3f} | {s['macro_f1_present_in_test']:.3f} | {s['f1_disease_risk']:.3f} |")
    out += ["", "| Condition | train | test | " + " | ".join(short[m] for m in methods) + " | P@10 | train prev. |"]
    out.append("|---|---|---|" + "---|" * (len(methods) + 2))
    for c, v in r["per_condition"].items():
        p10 = "–" if v["p_at_10"] is None else f"{v['p_at_10']:.2f}"
        out.append(f"| {c} | {v['train']} | {v['test']} | " + " | ".join(f"{v[m]:.2f}" for m in methods) + f" | {p10} | {v['train_prevalence']:.2f} |")
    ret = r["retrieval"]
    out += ["", f"Any-overlap P@k: {ret['any_overlap_p_at_k']} (random expectation {ret['any_overlap_random_expectation']})"]
    out += [f"Frequent-label macro P@k: {ret['frequent_label_macro_p_at_k']} (mean prevalence {ret['frequent_label_macro_prevalence']})"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("runs"))
    a = p.parse_args(argv)
    r = run(a.out)
    print((a.out / "m1_baselines.md").read_text())
    print(json.dumps(r["seconds"]), file=sys.stderr)


if __name__ == "__main__":
    main()

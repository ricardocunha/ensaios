# Results

Research demo, not a medical device. These numbers measure agreement with RFMiD's labels on its official test split; they say nothing about diagnosing patients.

## 1. Baselines on RFMiD (`make baselines`, 2026-10-01)

Setup:

- **Data:** RFMiD 1.0, official split. Index = 1,920 training images; choices made on the 640 validation images; numbers on the 640 test images. See [DATA.md](DATA.md).
- **Embeddings:** BiomedCLIP (`microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224`, HF revision `9f341de2…`), open_clip 3.3.0, torch 2.14.1, on MPS (M4 Pro). Embedding 3,200 images took 34.9 s (train 21.0 s, val 6.9 s, test 6.9 s); the whole run, including model load, 50 s.
- **Index:** Qdrant 1.19.1 (qdrant-client, local mode, cosine). 1,280 top-50 queries (val + test) in 1.4 s.
- **Frequent conditions:** the 16 with ≥ 20 training images (chosen from training counts only): DR, ARMD, MH, DN, MYA, BRVO, TSLN, LS, CSR, ODC, CRVO, ODP, ODE, RS, CRS, RPEC. 36 of the 45 conditions occur at least once in the test split.
- **Deterministic:** no sampling anywhere; seeds fixed at 0 anyway. Output: `runs/m1_baselines.json` / `.md` (git-ignored).

Methods:

- **all positive:** every label predicted for every image. An F1 floor, not a model.
- **kNN majority, k = 5:** a label is predicted when ≥ 3 of the 5 nearest training images carry it.
- **kNN weighted, k = 20, t = 0.20:** score = cosine-weighted share of the 20 nearest training images that carry the label; predicted when ≥ 0.20. k ∈ {1, 3, 5, 10, 20, 30, 50} and one global threshold ∈ {0.05 … 0.60} were chosen on validation (val macro-F1 over frequent conditions 0.367).
- **Zero-shot, p ≥ 0.5:** per label, a two-way softmax (BiomedCLIP's logit scale) between "fundus with *name, description*" and "healthy retina" prompts, each averaged over 3 templates. No RFMiD data used.
- **Zero-shot, validation thresholds:** the same scores with one threshold per label tuned on validation. That uses labelled data, so it's no longer zero-shot in the strict sense.

### Summary (test split)

| Method | macro-F1, 16 frequent | macro-F1, 36 present in test | F1 `Disease_Risk` (abnormal vs normal) |
|---|---|---|---|
| all positive (floor) | 0.108 | 0.053 | 0.883 |
| kNN majority, k = 5 | 0.264 | 0.127 | **0.931** |
| kNN weighted, k = 20, t = 0.20 | **0.339** | **0.160** | 0.923 |
| zero-shot, p ≥ 0.5 | 0.141 | 0.070 | 0.793 |
| zero-shot, val thresholds | 0.183 | 0.089 | 0.891 |

### Per condition (test F1; P@10 = share of the 10 retrieved training images carrying the label, over test images that have it)

| Condition | train | test | all positive | kNN maj. k5 | kNN w. k20 | ZS 0.5 | ZS val thr. | P@10 | train prevalence |
|---|---|---|---|---|---|---|---|---|---|
| Disease_Risk | 1519 | 506 | 0.88 | 0.93 | 0.92 | 0.79 | 0.89 | 0.86 | 0.79 |
| DR | 376 | 124 | 0.32 | 0.61 | 0.60 | 0.48 | 0.48 | 0.57 | 0.20 |
| ARMD | 100 | 31 | 0.09 | 0.23 | 0.47 | 0.14 | 0.16 | 0.26 | 0.05 |
| MH | 317 | 104 | 0.28 | 0.70 | 0.65 | 0.37 | 0.49 | 0.61 | 0.17 |
| DN | 138 | 46 | 0.13 | 0.04 | 0.23 | 0.08 | 0.14 | 0.15 | 0.07 |
| MYA | 101 | 32 | 0.10 | 0.62 | 0.68 | 0.17 | 0.20 | 0.50 | 0.05 |
| BRVO | 73 | 23 | 0.07 | 0.53 | 0.58 | 0.15 | 0.40 | 0.40 | 0.04 |
| TSLN | 186 | 53 | 0.15 | 0.24 | 0.45 | 0.14 | 0.16 | 0.27 | 0.10 |
| LS | 47 | 15 | 0.05 | 0.00 | 0.06 | 0.08 | 0.07 | 0.06 | 0.02 |
| CSR | 37 | 13 | 0.04 | 0.00 | 0.00 | 0.04 | 0.04 | 0.12 | 0.02 |
| ODC | 282 | 91 | 0.25 | 0.21 | 0.32 | 0.18 | 0.19 | 0.23 | 0.15 |
| CRVO | 28 | 9 | 0.03 | 0.36 | 0.59 | 0.09 | 0.30 | 0.21 | 0.01 |
| ODP | 65 | 24 | 0.07 | 0.00 | 0.00 | 0.08 | 0.08 | 0.03 | 0.03 |
| ODE | 58 | 17 | 0.05 | 0.56 | 0.67 | 0.12 | 0.12 | 0.35 | 0.03 |
| RS | 43 | 14 | 0.04 | 0.11 | 0.15 | 0.09 | 0.03 | 0.16 | 0.02 |
| CRS | 32 | 11 | 0.03 | 0.00 | 0.00 | 0.07 | 0.04 | 0.07 | 0.02 |
| RPEC | 22 | 4 | 0.01 | 0.00 | 0.00 | 0.00 | 0.01 | 0.05 | 0.01 |

### Retrieval quality (test queries against the training index)

| | @1 | @5 | @10 | random retrieval |
|---|---|---|---|---|
| Share of retrieved images sharing ≥ 1 label with the query (normal counts as a label) | 0.545 | 0.506 | 0.496 | 0.150 |
| Label precision, macro over the 16 frequent conditions | 0.328 | 0.265 | 0.252 | 0.062 (mean prevalence) |

"Random retrieval" is the expected value when neighbours are drawn uniformly from the training set (computed exactly, not sampled).

### Takeaways

- **Retrieval beats the text side of the same model, by a lot.** kNN over BiomedCLIP image embeddings reaches macro-F1 0.339 on the frequent conditions; zero-shot with the same model's text encoder reaches 0.141 (0.183 with validation thresholds), barely above the all-positive floor (0.108). On normal-vs-abnormal, zero-shot at 0.5 (0.793) is *below* the floor (0.883).
- **Zero-shot probabilities aren't calibrated.** The validation-tuned thresholds range from 0.03 (RPEC) to 0.999 (BRVO): a fixed 0.5 means something different for every label.
- **Retrieved neighbours carry signal.** Half the top-10 neighbours share a label with the query, vs 15% at random; per condition, P@10 is roughly 3× (DR) to 14× (CRVO) the training prevalence for DR, MH, MYA, BRVO, ODE and CRVO.
- **Where kNN works, and where it doesn't.** Conditions with a striking global look (MYA, ODE, MH, BRVO, CRVO) get F1 0.58–0.68. Small or subtle findings (DN drusen, LS laser scars, CSR, ODP pallor, CRS, RPEC) get 0.00–0.23: a 224-px global embedding doesn't see them. ODC (cup-to-disc) is common (282 training images) and still only 0.32.
- **MH (media haze) is among the best labels for kNN (0.65–0.70)**, and it describes the photo's clarity as much as the eye; the embedding may be matching image quality.
- **The long tail is out of reach for any of these.** Over all 36 conditions present in test, the best macro-F1 is 0.160; 29 of the 45 conditions have < 20 training images.
- **Caveat on kNN:** at least two test images have a near-identical training photo of the same eye with a *different* label (DATA.md). Retrieval can match the eye rather than the disease, and the labels themselves disagree in places.

What this sets up for Milestone 2: the VLM + retrieval system has to beat **0.339** (frequent macro-F1) and **0.931** (`Disease_Risk` F1) on this split, and zero-shot VLM has to beat 0.141 to be worth its cost.

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

## 2. Milestone 2 (2026-10-02)

Same setup as section 1 (official split, index = 1,920 training images, choices on validation). New: a same-eye audit and an exclusion list, a hybrid Qdrant index, and a local vision-language model.

### 2.1 Same-eye audit and the "deduplicated" test split (`make dedup`, `make m2-baselines`)

How the audit works and how its thresholds were set: [DATA.md, "Duplicate audit"](DATA.md#duplicate-audit-milestone-2-2026-10-02). In short: every one of the 5.1 M image pairs was checked with a geometric match of the retina's vessel pattern (SIFT + RANSAC); 154 pairs among 263 images show the same eye, 70 of them across splits, and 83 of the 154 pairs (54 %) carry different label sets. **31 test images** (and 28 validation images) have a same-eye image in an earlier split; they are listed in `docs/exclusions.json` and left out of every "deduplicated" number from here on. Deduplicated test = **609** images.

The M1 baselines, unchanged (same k, thresholds and prompts), scored on all 640 test images and on the 609 deduplicated ones (`runs/m2_baselines_dedup.json`):

| Method | macro-F1, 16 frequent: all | dedup | F1 `Disease_Risk`: all | dedup | macro-F1 on the 31 excluded only |
|---|---|---|---|---|---|
| all positive (floor) | 0.108 | 0.107 | 0.883 | 0.881 | 0.109 |
| kNN majority, k = 5 | 0.264 | 0.268 | 0.931 | 0.935 | 0.260 |
| kNN weighted, k = 20, t = 0.20 | 0.339 | **0.341** | 0.923 | 0.925 | 0.380 |
| zero-shot, p ≥ 0.5 | 0.141 | 0.143 | 0.793 | 0.799 | 0.111 |
| zero-shot, val thresholds | 0.183 | 0.186 | 0.891 | 0.889 | 0.105 |

- **Duplicates did not inflate kNN.** Without the 31 affected test images, kNN weighted scores 0.341 instead of 0.339: none of its score came from same-eye matches (the excluded images are a bit easier, 0.380, but they are 5 % of the split). Re-tuning k and t on the deduplicated validation split picks the same k = 20, t = 0.20 (val macro-F1 0.370).
- **Why not:** BiomedCLIP rarely retrieves the same eye. Of the 22 excluded test images whose same-eye partner is in the training index, the partner is the top-1 neighbour for only **5**, and only 2 of those 5 have the same labels as the test image. Most same-eye pairs are different photos (another field of view, camera or exposure), and a global 224-px embedding doesn't key on the vessel pattern.
- Retrieval quality moves the same way (dedup vs all): top-1 neighbour shares a label 55.0 % vs 54.5 %; frequent-label macro P@10 0.253 vs 0.252.
- The real cost of the duplicates is **label noise**, not leakage: in 7 of the 8 near-identical photo pairs, the two copies have different labels.

### 2.2 Hybrid retrieval: dense image vectors + sparse "report" text (`make retrieval`)

- **No free text in RFMiD.** Each training image gets a deterministic "report" built from its labels and the fixed one-line descriptions in `eye_rag.labels` (e.g. "diabetic retinopathy (DR): microaneurysms, dot and blot hemorrhages and hard exudates."). It contains nothing that the labels don't.
- **Index:** one Qdrant collection (`rfmid_hybrid`), dense vector `image` (BiomedCLIP, cosine) + sparse vector `report` (bag of words, Qdrant IDF modifier). Hybrid = Reciprocal Rank Fusion (`Fusion.RRF`) of the top 50 from each side.
- **The query side.** A test image has no labels, so its text must come from something available at test time:
  - `hybrid_knn` (the method): a report built from the **kNN pre-labels** (the M1 kNN: labels with weighted share ≥ 0.20 among the 20 nearest training images). It needs no extra model, but it recycles the dense neighbours' labels, so the sparse side re-ranks towards cases that agree with the kNN vote.
  - `hybrid_vlm`: a report built from the VLM's zero-shot labels (arm a below), on the VLM subset.
  - `hybrid_oracle`: a report from the query's **true** labels. Uses test labels; an upper bound only, never a method.

Label precision@k (deduplicated splits; "frequent macro" = mean over the 16 frequent conditions of the share of the k retrieved cases carrying the query's condition; "any overlap" = share of retrieved cases sharing ≥ 1 label with the query, normal counting as a label). `runs/m2_retrieval.json`:

| Retrieval | split | frequent macro P@1 | P@3 | P@5 | P@10 | any-overlap P@1 | P@3 | P@5 | P@10 |
|---|---|---|---|---|---|---|---|---|---|
| dense only | val (612) | 0.305 | 0.274 | 0.265 | 0.250 | 0.515 | 0.505 | 0.493 | 0.478 |
| hybrid_knn | val (612) | 0.313 | **0.321** | 0.321 | 0.318 | 0.533 | **0.547** | 0.546 | 0.544 |
| hybrid_oracle (upper bound) | val (612) | 0.382 | 0.527 | 0.567 | 0.604 | 0.554 | 0.687 | 0.716 | 0.744 |
| dense only | test (609) | 0.330 | 0.277 | 0.271 | 0.253 | 0.550 | 0.522 | 0.513 | 0.502 |
| hybrid_knn | test (609) | 0.334 | **0.329** | 0.322 | 0.316 | 0.553 | **0.577** | 0.571 | 0.568 |
| hybrid_vlm (query = VLM zero-shot labels) | test (609) | 0.329 | 0.243 | 0.220 | 0.216 | 0.550 | 0.486 | 0.465 | 0.461 |
| hybrid_oracle (upper bound) | test (609) | 0.366 | 0.540 | 0.569 | 0.615 | 0.571 | 0.705 | 0.722 | 0.754 |

- Hybrid with kNN-derived query text beats dense only at k ≥ 3 on both splits (frequent macro P@3 0.329 vs 0.277 on test; any-overlap P@3 0.577 vs 0.522). At k = 1 they're nearly equal: RRF keeps the best dense hit on top.
- **A worse query text makes hybrid worse than dense.** With the VLM's zero-shot labels as the query text, precision drops below dense only (P@3 0.243 vs 0.277): the VLM calls 60 % of test images "media haze" (366 of 609, vs 103 true), and the sparse side then pulls in hazy cases. Hybrid is only as good as the text you can honestly put in the query.
- The oracle row shows how much a good text query could add (P@10 0.615 vs 0.253), and why it can't be used: the text side is the labels.
- **Choice for the VLM arm (on validation):** `hybrid_knn`, k = 3 cases (val frequent macro P@3 0.321 vs 0.274 dense).

### 2.3 VLM zero-shot vs VLM + retrieved cases vs kNN (`make vlm-zero-shot vlm-retrieval m2-score`)

- **Model:** Qwen3-VL-8B-Instruct, 4-bit, local through mlx-vlm (`mlx-community/Qwen3-VL-8B-Instruct-4bit@defcdea7`), greedy decoding, typed JSON answer (labels from the fixed RFMiD list, or `normal`), up to 2 retries with the validation error. Prompt fixed in `eye_rag.vlm`.
- **Arms:** zero-shot (query photo only); retrieval (the 3 `hybrid_knn` cases from 2.2, each image with its label-report, then the query); kNN weighted (M1 method, unchanged).
- **Images:** all 609 deduplicated test images. Prompt and k checked on a 20-image validation pilot only.

All 609 test images (`runs/m2_three_arms_test.{json,md}`):

| Arm | macro-F1, 16 frequent | F1 `Disease_Risk` | s / image |
|---|---|---|---|
| VLM zero-shot | 0.058 | 0.872 | 5.2 |
| VLM + 3 retrieved cases | 0.298 | 0.899 | 7.5 |
| kNN weighted (k = 20, t = 0.20) | **0.341** | **0.925** | < 0.01 |

Per condition (F1; positives in brackets): DR (117) 0.18 / 0.58 / 0.60 · MH (103) 0.42 / 0.51 / 0.65 · ODC (88) 0.00 / 0.23 / 0.32 · TSLN (50) 0.09 / 0.32 / 0.43 · MYA (32) 0.04 / 0.46 / 0.68 · BRVO (20) 0.10 / 0.60 / 0.59 · ODE (17) 0.00 / 0.54 / 0.67 · CSR (12) 0.00 / 0.13 / 0.00 · CRS (10) 0.00 / 0.18 / 0.00. Full table in the run file.

- **Zero-shot VLM is below the all-positive floor** (0.058 vs 0.107): it names one finding per image on average (1.13), and that finding is usually media haze.
- **Retrieved cases add 0.24 macro-F1**, but the VLM + retrieval arm still loses to the kNN vote it is built on (0.298 vs 0.341), and costs ~7.5 s per image instead of a vector lookup. It wins only on a few rare conditions where kNN's threshold rarely or never fires (CSR 0.13 vs 0.00, CRS 0.18 vs 0.00, LS 0.11 vs 0.06; 10–12 positives each, so these are a handful of images), and narrowly on BRVO (0.60 vs 0.59).
- **Most of what it says comes from the cases.** In 74 % of answers every predicted label appears in one of the 3 cases shown. Section 2.4 tests whether it is reading the photographs or the labels.
- **The diagnosis step's own citations** (`cited_cases`, no extra call): 64.7 % of answers cite at least one case, none cite a case that doesn't exist, and in 90.1 % of the citing answers every cited case shares a label with the answer.
- Reliability: 0 failed answers in 1,218 calls; 1 retry (zero-shot).

### 2.4 Explanation agent, citation check and the shuffled-labels test (`make vlm-shuffled explain explain-shuffled explain-score`)

**Shuffled labels (faithfulness test).** The retrieval arm again, on the same 609 images with the same 3 retrieved case *images*, but each case shown with the recorded findings of a random other training case, never one of the query's real case label sets (`eye_rag.diagnose.shuffled_case_labels`, seeded per query). If the model compares photographs, its answer should barely move.

| Arm (same 609 images) | macro-F1, 16 frequent | F1 `Disease_Risk` |
|---|---|---|
| VLM zero-shot | 0.058 | 0.872 |
| VLM + cases, true labels | 0.298 | 0.899 |
| VLM + cases, **shuffled labels** | **0.056** | 0.887 |

- **Shuffling the labels erases the whole retrieval gain** (0.298 → 0.056, back to zero-shot). The case photographs alone add nothing measurable; the text next to them does all the work.
- **58 % of answers change** when only the labels change.
- Share of answer labels found in the cases' *shown* labels: 76 % with true labels, 60 % with shuffled ones. Only 34 % of the shuffled-run answer labels are in the hidden, true labels of the cases it was looking at.
- **Injected labels:** in 29 % of images (205 labels in total) the shuffled run gives a label that is in the shown (wrong) text, in none of the real cases, not in the zero-shot answer, and not true for the image. Only the wrong text explains it.

**Explanation agent + citation check** (`eye_rag.explain`; same VLM, greedy). For each diagnosed label the model says whether it comes from the photo (`image`), the cases (`cases`) or `both`, and cites case numbers. A deterministic check then verifies: each diagnosed label explained exactly once; cited cases exist; source agrees with citations; **each cited case's recorded findings contain the label it is cited for**. Problems go back to the model as a list, up to 2 retries; an answer that still fails is kept and marked unverified. Run on both arms' diagnoses (`runs/m2_explain_test.json`):

| | true labels | shuffled labels |
|---|---|---|
| verified at first try | 60.3 % | 51.1 % |
| verified after ≤ 2 retries | **90.0 %** | **89.3 %** |
| unverified | 61 | 65 |
| case citations in verified explanations | 549 | 344 |
| … where the cited label is true for the image | **48.8 %** | **12.2 %** |
| verified findings sourced "image" only | 28 % (214 of 763) | 49 % (336 of 680) |
| s / image | 11.9 | 12.9 |

- **The check passes as often on wrong labels as on right ones** (90.0 % vs 89.3 %). It verifies that a citation matches the text the model was shown, and it does that job: first-try problems were mostly a case cited for a label it doesn't carry (296 with true labels, 520 shuffled) and labels explained that weren't diagnosed (70 / 244), and retries fixed most of them. It cannot tell whether the shown text was true.
- **A verified citation is not a correct one.** Even with true labels, under half of the verified case citations name a label the image actually has (48.8 %); with shuffled labels, 12.2 %.
- **Explanations claim the photo.** Almost every cited finding is sourced "both" (seen in the photo *and* in the cases), and with shuffled labels the share sourced "image" alone rises to 49 %. The diagnoses moved with the text (above), so these "I see it in the photo" claims are not evidence that it did.
- **Example (test/205):** the image is labelled DR; its 3 real nearest cases are all DR, and the true-label run answers DR. Shown the same 3 photos with case 1 relabelled ARMD and cases 2–3 relabelled normal, the model answers ARMD, cites case 1, and explains: "The QUERY photograph shows signs of age-related macular degeneration, consistent with the finding in reference case 1, which was also labeled ARMD." Source "both"; verified on the first try.
- Unverified explanations are mostly the same mistake repeated after feedback, e.g. in the validation pilot (`val/81`), citing three myopia cases for tessellation, which none of them records, because MYA "is associated with tessellation". The prompt was not tuned to pass the check (20-image validation pilot only).

What this sets up for the evaluation milestone: on this dataset the VLM + retrieval system does not beat the kNN vote it is built on, its gain comes from reading the retrieved labels, and a citation check measures consistency with the retrieved text, not correctness or faithfulness to the image. The shuffled-labels arm is the test that shows it.

## 3. Evaluation: how sure are these differences? (`make evaluate`, 2026-10-05)

Paired bootstrap over the 609 deduplicated test images, 2,000 resamples, seed 0 (`eye_rag.m4`, `runs/m4_eval.json`). Each resample re-scores every arm on the same images. Macro-F1 averages over the frequent conditions present in the resample; citation rates resample images, not citations. No model is called; it reads the Milestone 2 run files.

| Arm | macro-F1, 16 frequent (95 % CI) | F1 `Disease_Risk` (95 % CI) |
|---|---|---|
| kNN weighted | **0.341** (0.304–0.380) | **0.925** (0.907–0.941) |
| VLM + 3 cases, true labels | 0.298 (0.249–0.344) | 0.899 (0.878–0.917) |
| VLM + 3 cases, shuffled labels | 0.056 (0.044–0.069) | 0.887 (0.866–0.906) |
| VLM zero-shot | 0.058 (0.042–0.077) | 0.872 (0.848–0.893) |

| Paired difference in macro-F1 | point | 95 % CI |
|---|---|---|
| VLM + cases − kNN | −0.043 | −0.084 to −0.006 |
| VLM + cases − VLM zero-shot | +0.240 | +0.187 to +0.286 |
| VLM + cases (true) − VLM + cases (shuffled) | +0.243 | +0.192 to +0.286 |
| VLM + cases (shuffled) − VLM zero-shot | −0.002 | −0.023 to +0.016 |

| Faithfulness and explanations | true labels | shuffled labels |
|---|---|---|
| answers that change when only the case labels change | – | 58.0 % (54.0–61.6) |
| explanations verified by the citation check | 90.0 % (87.5–92.3) | 89.3 % (86.9–91.8) |
| verified case citations naming a label the image has | 48.8 % (44.8–53.1), of 549 | 12.2 % (9.0–15.6), of 344 |

- **VLM + retrieval is worse than the kNN vote it is built on**, and the interval excludes zero, though only just (upper end −0.006). "Not better" is the safe reading; "worse by about 0.04" is the point estimate.
- **The whole retrieval gain is the labels.** With shuffled labels the arm is indistinguishable from zero-shot (−0.002, CI −0.023 to +0.016), and the true-vs-shuffled gap (+0.243) is the same size as the retrieval gain over zero-shot (+0.240).
- **The citation check doesn't separate true from shuffled labels**: 90.0 % vs 89.3 %, a 0.7-point gap inside either interval's ±2.4-point width. What it verifies (citation matches shown text) holds either way; what we'd want (cited label is right) drops from 48.8 % to 12.2 %.
- `Disease_Risk` (normal vs abnormal) barely moves across arms (0.87–0.92), and is near the all-positive floor (0.881): 79 % of test images are abnormal, so this label says little about any of the methods.

### Limits of these numbers

- One dataset (RFMiD 1.0: 3 cameras, one hospital network in India), one split, one VLM (Qwen3-VL-8B, 4-bit), one prompt, greedy decoding. The intervals cover resampling of images, not a different model, prompt, k or dataset.
- Labels are the reference, and they disagree with themselves: 7 of 8 near-identical photo pairs have different label sets (DATA.md). Every F1 here is agreement with these labels, not diagnostic accuracy.
- Camera is not in the label files, so a possible camera shortcut in kNN (and so in the cases shown to the VLM) is untested.
- RFMiD 2.0 (out-of-distribution check) and BRSET were not run (Milestone 3, optional).

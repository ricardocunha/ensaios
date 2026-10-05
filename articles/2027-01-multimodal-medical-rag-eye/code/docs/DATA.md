# Data

Research demo, not a medical device: see the [article README](../../README.md). Nothing in this folder supports a clinical decision.

## What we use

| Source | What | License / terms | In git? |
|---|---|---|---|
| **RFMiD 1.0** (Pachade et al. 2021), via the Hugging Face mirror [`ctmedtech/RFMID`](https://huggingface.co/datasets/ctmedtech/RFMID), pinned to revision `16ee0cf5…` | 3,200 colour fundus photos, 45 condition labels + `Disease_Risk`, official split 1,920 / 640 / 640 | CC BY 4.0 as stated by the mirror [[VERIFY: licence on the official IEEE DataPort page, which needs a login to read in full; the mirror card, the Kaggle copy (per the `bumbledeep/rfmid` card) and the authors' own RFMiD 2.0 Zenodo record all say CC BY 4.0]] | **No** (downloaded to `data/rfmid/`) |
| **RFMiD 2.0** (Panchal et al. 2023), [Zenodo 10.5281/zenodo.7505822](https://doi.org/10.5281/zenodo.7505822), uploaded by the authors | 860 fundus photos, 51 label columns, split 509 / 177 / 174 | CC BY 4.0 (Zenodo record) | **No**. Not used in Milestone 1; reserved as an out-of-distribution check |
| BiomedCLIP `microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224` (HF revision `9f341de2…` on 2026-10-01) | Image and text encoder | MIT. The model card limits intended use to research; "any deployed use case … is currently out of scope" | No (HF cache) |
| **Qwen3-VL-8B-Instruct**, 4-bit MLX conversion [`mlx-community/Qwen3-VL-8B-Instruct-4bit`](https://huggingface.co/mlx-community/Qwen3-VL-8B-Instruct-4bit), revision `defcdea7…` (of [`Qwen/Qwen3-VL-8B-Instruct`](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)) | Vision-language model for the diagnosis arms (Milestone 2), run locally with mlx-vlm 0.7.4 | Apache-2.0 (both repos), not gated, no account | No (HF cache, 5.8 GB) |
| MedGemma 4B (`google/medgemma-4b-it`) | Considered, **not used** | Health AI Developer Foundations Terms of Use (last modified 2024-11-15): research use is allowed and Google claims no ownership of outputs (§3.3), so publishing results would be fine; clinical use needs regulatory authorisation (§3.1–3.2). But the official repo is **gated** (an HF account and accepting the terms), and this project doesn't sign up for anything; the ungated community re-uploads carry the same terms and skip the acceptance step, so we don't use them either | — |
| `tests/` fixtures | Synthetic label CSVs, random images and vectors | Ours | Yes |

### Citation requirements

CC BY 4.0 requires attribution. The article and the code README cite:

- S. Pachade, P. Porwal, D. Thulkar, M. Kokare, G. Deshmukh, V. Sahasrabuddhe, L. Giancardo, G. Quellec, F. Mériaudeau. *Retinal Fundus Multi-Disease Image Dataset (RFMiD): A Dataset for Multi-Disease Detection Research.* Data 2021, 6(2), 14. doi:10.3390/data6020014. Dataset: IEEE DataPort, doi:10.21227/s3g7-st65.
- RFMiD 2.0 (when used): S. Panchal et al., Zenodo, doi:10.5281/zenodo.7505822 [[VERIFY: the companion data paper's exact citation (Data 2023, "Retinal Fundus Multi-Disease Image Dataset (RFMiD) 2.0: A Dataset of Frequently and Rarely Identified Diseases")]].
- BRSET (mentioned, not used): L. F. Nakayama et al., *A Brazilian Multilabel Ophthalmological Dataset (BRSET)*, PhysioNet v1.0.2; data paper in *PLOS Digital Health*, 2024. Counts (16,266 photos, 8,524 patients, three centres in São Paulo, 2010–2020) and access terms from the PhysioNet page.
- BiomedCLIP: S. Zhang et al., *BiomedCLIP: a multimodal biomedical foundation model pretrained from fifteen million scientific image-text pairs*, 2023 (arXiv:2303.00915) [[VERIFY: final venue]].

## Why RFMiD (and why not BRSET, for now)

The plan was BRSET (see [PLAN.md](../../PLAN.md)). BRSET needs PhysioNet credentialed access, and this project doesn't sign up for accounts, so we picked the best dataset that downloads without one. Requirements: real disease labels (ideally multi-label, since the article is about retrieval *explaining* several findings), an official split, a licence that allows research use and publishing derived results, and < ~5 GB on disk.

### Candidates (checked 2026-10-01)

| Dataset | Images | Labels | Official split | Licence / terms | Download without an account? | Verdict |
|---|---|---|---|---|---|---|
| **RFMiD 1.0** | 3,200 (3 cameras, India) | Multi-label: 45 conditions + `Disease_Risk` | 1,920 / 640 / 640 | CC BY 4.0 [[VERIFY: see above]] | Official host: no (IEEE DataPort, "accessible to all logged in users"; RIADD on grand-challenge also needs login). **CC BY mirror on Hugging Face: yes** | **Chosen** |
| **RFMiD 2.0** | 860 | Multi-label: 51 columns (incl. `WNL` normal) | 509 / 177 / 174 | CC BY 4.0 | Yes (Zenodo, 64 MB) | **Second dataset**, later, as an external check. Too small to be the index |
| MuReD | 2,208 | Multi-label: 20 | train / val CSVs, no test | CC BY 4.0 (Mendeley Data) | Yes (5.4 GB zip) | Not chosen: built from ARIA, STARE and **RFMiD** images (overlaps our test set), no test split, 5.4 GB |
| IDRiD (grading part) | 516 | DR grade 0–4 + macular-edema grade 0–2 | 413 / 103 | CC BY 4.0 per the third-party mirrors [[VERIFY: IEEE DataPort page]] | Official: no (IEEE DataPort login). Mirrors: yes (Zenodo 10.5281/zenodo.17219542, uploaded by a third party; HF `amin-nejad/idrid-disease-grading`) | Not chosen: single disease, 103 test images |
| JSIEC "1000 fundus images with 39 categories" | 1,000 | Single-label, 39 classes | none | Zenodo `other-open` [[VERIFY: what the licence actually says]] | Yes (Zenodo 10.5281/zenodo.3477553, 403 MB) | Not chosen: no official split, unclear licence, ~25 images per class |
| ODIR-5K | ~10,000 (5,000 patients, both eyes) | 8 patient-level categories (N, D, G, C, A, H, M, O) | train + off-site/on-site test | Unclear: site says only that data follows China's privacy rules [[VERIFY: terms]]. HF copies claim MIT, which the uploader can't grant | No (grand-challenge login; Kaggle copies need a Kaggle account) | Not chosen: account, licence unclear, labels per patient, not per image |
| APTOS 2019 | 3,662 train (+1,928 test with hidden labels) | DR grade 0–4 | test labels not released | Kaggle competition data: "Competition Use and Non-Commercial & Academic Research" (as reported by third parties) [[VERIFY: rules page, which needs a login]] | No (Kaggle account + accepting rules). HF re-uploads have no licence from the owner | Not chosen: account, single disease, no labelled test |
| EyePACS (Kaggle DR 2015) | 35,126 train + 53,576 test [[VERIFY]] | DR grade 0–4 | train / test | Kaggle competition rules [[VERIFY]] | No (Kaggle account); ~80 GB [[VERIFY]] | Not chosen: account, size, single disease |
| Messidor-2 | 1,748 (874 exams) | **None in the official release** (third-party DR grades exist) | none | Free for research and education; no redistribution | No (form with personal data, emailed link) | Not chosen |
| DDR | 13,673 (147 hospitals, China) | DR grade (6 levels incl. ungradable) [[VERIFY]] + lesions on 757 | 6,835 / 2,733 / 4,105 | CC BY-NC-SA 4.0 | Google Drive / Baidu links; Drive folder may work without login [[VERIFY]] | Not chosen: single disease; NC-SA |
| AIROGS (Rotterdam EyePACS) | ~100k [[VERIFY]] | Referable glaucoma yes/no | train + hidden test | CC BY-NC-ND 4.0 (Zenodo) | Yes, but 54 GB train set | Not chosen: single label, size, ND |
| **BRSET** | 16,266 photos, 8,524 patients (Brazil) | Multi-label: 13 conditions + DR grades, anatomy, quality, demographics | — | PhysioNet Credentialed Health Data License 1.5.0 + DUA | **No**: credentialed PhysioNet account, CITI training, signed DUA | Deferred (see below) |

HF mirrors of everything above exist; we only use a mirror when the original licence permits redistribution (CC BY does; competition rules and "no redistribution" terms don't, whatever licence tag the mirror carries).

### What BRSET would add

- **Brazilian patients**: three ophthalmology centres in São Paulo, 2010–2020, Nikon NF505 and Canon CR-2 cameras (PhysioNet page, v1.0.2).
- **5× the images** of RFMiD (16,266 vs 3,200), so a denser retrieval index.
- **Richer labels**: DR on two scales (ICDR, SDRG), macular edema, toxoplasmosis scar, nevus, hypertensive retinopathy, etc., plus image-quality fields (focus, illumination, field, artefacts) and demographics (age, sex, diabetes history). Quality labels would let us test whether retrieval fails on bad photos.
- Its DUA says: "If I openly disseminate my results, I will also contribute the code used to produce those results to a repository that is open to the research community." This repo already does that. It also forbids sharing the data and any attempt at re-identification.

## RFMiD: what's in it

Label counts per official split (`make stats`, 2026-10-01):

| Code | train | val | test |
|---|---|---|---|
| (images) | 1920 | 640 | 640 |
| normal (Disease_Risk = 0) | 401 | 134 | 134 |
| DR | 376 | 132 | 124 |
| MH | 317 | 102 | 104 |
| ODC | 282 | 72 | 91 |
| TSLN | 186 | 65 | 53 |
| DN | 138 | 46 | 46 |
| MYA | 101 | 34 | 32 |
| ARMD | 100 | 38 | 31 |
| BRVO | 73 | 23 | 23 |
| ODP | 65 | 26 | 24 |
| ODE | 58 | 21 | 17 |
| LS | 47 | 17 | 15 |
| RS | 43 | 14 | 14 |
| CSR | 37 | 11 | 13 |
| CRS | 32 | 11 | 11 |
| CRVO | 28 | 8 | 9 |
| RPEC | 22 | 6 | 4 |
| AION | 17 | 5 | 4 |
| AH | 16 | 4 | 5 |
| MS | 15 | 5 | 7 |
| EDN | 15 | 5 | 4 |
| ERM | 14 | 7 | 5 |
| RT | 14 | 6 | 5 |
| PT | 11 | 2 | 4 |
| MHL | 11 | 3 | 3 |
| TV | 6 | 2 | 2 |
| RP | 6 | 2 | 2 |
| ST | 5 | 4 | 2 |
| PTCR | 5 | 1 | 0 |
| CME | 4 | 1 | 2 |
| CWS | 3 | 3 | 2 |
| MNF | 3 | 0 | 0 |
| TD | 3 | 2 | 4 |
| CF | 3 | 2 | 1 |
| PRH | 2 | 1 | 2 |
| CRAO | 2 | 2 | 0 |
| BRAO | 2 | 2 | 0 |
| CB | 1 | 0 | 1 |
| VH | 1 | 2 | 1 |
| MCA | 1 | 0 | 0 |
| VS | 1 | 3 | 0 |
| PLQ | 1 | 1 | 0 |
| HPED | 1 | 0 | 0 |
| CL | 1 | 0 | 1 |
| ODPM | 0 | 2 | 0 |
| HR | 0 | 0 | 1 |

Notes on label quality:

- **Multi-label.** In training, 401 images are normal, 1,061 have one condition, 373 two, 79 three, 6 four or five.
- **Long tail.** 16 conditions have ≥ 20 training images; 16 have ≤ 3; `ODPM` and `HR` have **zero** training images (they appear only in validation/test). We report macro-F1 over the 16 *frequent* conditions (chosen from training counts only) and, separately, over every condition present in the test split.
- **`Disease_Risk`** is "any condition present", so it's a normal-vs-abnormal label, 79% positive in training.
- **`MH` (media haze)** is the third most common label (317 training images). It describes the photo's clarity as much as the eye, and fundus photos of cataract patients look hazy; a model can learn it from image quality.
- The labels come from "adjudicated consensus of two senior retinal experts" (paper abstract, quoted in the mirror cards). We haven't audited them.
- **The same eye appears in several images, across splits, sometimes with different labels.** Milestone 1 spotted two cases by eye (`test/541` DN vs `train/1877` normal; `test/571` normal vs `train/1818` ODC). Milestone 2 ran a full audit over all 5.1 M image pairs: see "Duplicate audit" below. Result: 154 same-eye pairs among 263 images, 70 of them across splits; **31 test and 28 validation images** have a same-eye image in an earlier split and are excluded from the "deduplicated" numbers (`docs/exclusions.json`).
- The images come from three cameras with different resolutions and fields of view; camera is not in the label files, so a kNN index can match on camera instead of disease. Not checked yet (still open after Milestone 2).

## Duplicate audit (Milestone 2, 2026-10-02)

`make dedup` (`eye_rag.dedup`) checks **every** pair of the 3,200 images (5,118,400 pairs) and writes the exclusion list `docs/exclusions.json` (committed; ids only, no images). The official split is not changed: later evaluations report both "all" and "deduplicated" (= minus the excluded images).

**Signals.** Three per pair:

1. BiomedCLIP image cosine (the M1 embeddings).
2. A 64-bit perceptual hash (DCT pHash, as in `imagehash.phash`) of the fundus disc, after cropping the black surround.
3. A geometric match of the retina: SIFT keypoints on the green channel (Gaussian blur σ 1.5, then CLAHE; 512 px; only the inner 85 % of the disc, which drops the rim and the camera's notch), Lowe ratio test 0.75, matches made **one-to-one**, and a RANSAC similarity transform (5 px). The score is the number of RANSAC inliers, and it's zeroed unless the transform looks like a re-photograph (scale 0.8–1.25, rotation ≤ 30°). 54.7 s for the features, 620 s to match all pairs (one CPU process, `nice`).

**How the thresholds were set (by looking at pairs, not by a metric).** We made side-by-side contact sheets of pairs in score bands and looked at them (scripts not kept; the bands are reproducible from `runs/dedup_pairs.json` and the cached matrix `data/embeddings/pair_inliers.npz`):

- **Cosine alone can't do it.** BiomedCLIP puts every fundus photo close together: 1,587 pairs have cosine ≥ 0.99 and 48,343 ≥ 0.98. Of the 12 closest cross-split pairs, 3 pass the geometric check (the two known duplicates and `train/1456`–`val/244`); the other 9 looked like different eyes with a similar layout and colour, and score 0–4 inliers. Only 8 of the 1,587 pairs at ≥ 0.99 pass the geometric check; same-eye pairs have cosines as low as 0.84 (median 0.96).
- **pHash alone can't do it either.** Pairs at Hamming distance ≤ 2 (191 pairs) were mostly different eyes with the disc in the same place and similar brightness; 2 of them pass the geometric check. Same-eye pairs have a median Hamming distance of 19 (of 64): a different field of view, exposure or camera changes the hash completely.
- **A first version of the geometric match had false positives**: different eyes with 60–200 "inliers". Two causes, both fixed before the full run: small-scale noise keypoints (fixed by the blur), and many-to-one matches collapsing onto one textured spot (fixed by one-to-one matching). A high-pass vessel cross-correlation we also tried was dominated by camera artefacts (dust blotches on hazy photos) and was dropped.
- **With the final matcher**, random pairs score 0–5 inliers (5,083,788 pairs score 0; only 218 of 5.1 M pairs reach ≥ 6). Looking at the bands: 6–7 inliers were different eyes; **8–14 is a grey zone** (roughly half the pairs we looked at were clearly the same eye, often photographed with a different centre, e.g. disc-centred vs macula-centred); ≥ 15 were mostly the same eye, including one normal eye photographed seven times (5 train, 1 val, 1 test) with different cameras and exposures. Thumbnails can't settle every pair, so these are judgements, not counts.
- **Threshold: ≥ 8 inliers** for the exclusion list, on purpose on the generous side: wrongly excluding a test image costs a little sample size, wrongly keeping a same-eye image leaks. Numbers at ≥ 15 are reported too.

**Counts** (`runs/dedup_pairs.json`):

| Pair of splits | same-eye pairs (≥ 8 inliers) | … with different labels | pairs at ≥ 15 inliers | … with different labels |
|---|---|---|---|---|
| train–train | 61 | 33 | 48 | 26 |
| train–val | 33 | 21 | 25 | 16 |
| train–test | 26 | 14 | 20 | 10 |
| val–val | 12 | 4 | 11 | 3 |
| val–test | 11 | 6 | 7 | 3 |
| test–test | 11 | 5 | 5 | 0 |
| **total** | **154** (263 images) | **83** | 116 | 58 |

- **Cross-split:** 70 pairs (≥ 8 inliers), 52 at ≥ 15.
- **Excluded:** 31 test images (21 at ≥ 15) and 28 validation images (20 at ≥ 15). Deduplicated test = **609** images; all 36 conditions present in the test split are still present.
- **Label disagreement is common within same-eye pairs: 83 of 154 pairs (54 %)**. Some is legitimate (a different field of view can show a finding the other photo doesn't, e.g. laser scars at the edge); some is not: among the 8 pairs that are near-identical photos (cosine ≥ 0.99 and geometric match), **7 have different label sets**. That bounds what any method can score against these labels, and it means a "wrong" answer on such an image may be annotator disagreement.
- **Recall is unknown.** A same-eye pair whose vessels can't be matched (heavy media haze, very different fields) isn't found. The audit can only under-count.

## The mirror: what we check, what we can't

- The mirror holds 1,920 / 640 / 640 PNGs and the three official label CSVs (`RFMiD_Training_Labels.csv`, `RFMiD_Validation_Labels.csv`, `RFMiD_Testing_Labels.csv`), matching the split sizes stated on IEEE DataPort.
- `download` checks every PNG against the SHA-256 the Hub stores for it and refuses a row-count mismatch. That proves the files are the mirror's files at the pinned revision, **not** that the mirror equals the official release [[VERIFY: compare against the official zip if someone with an IEEE account can share checksums]].
- The mirror's card is partly wrong (it describes JPG files named `IDRiD_001.jpg` and a metadata CSV that isn't there). The files themselves are PNGs named `<n>.png`. The repo also holds two stray model files under `Training_Set/Training_Set/models/`, which we don't download.

## Storage

- The originals are ~8.2 GB of PNGs (train 4.68 GB, val 1.56 GB, test 1.74 GB). `download` streams each one, verifies it, and keeps a JPEG copy with the long side at 1,024 px (quality 92) in `data/rfmid/<split>/<n>.jpg`. After the download on 2026-10-01: 3,200 files, 7.99 GB transferred, **228 MB** kept in `data/rfmid/`; embeddings (6.8 MB) and the Qdrant folder (10 MB) bring `data/` to 245 MB.
- BiomedCLIP looks at 224 × 224 px, so 1,024 px is enough for this milestone and leaves room for a vision-language model later.
- `data/rfmid/<split>_manifest.jsonl` records each original file's SHA-256 and size.

## Personal data

RFMiD images are de-identified fundus photos with no metadata beyond the labels. A retinal photo is still biometric-like data, so images never go into git, and the article shows at most a few thumbnails under CC BY attribution.

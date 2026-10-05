# Glossary

- **Fundus photo**: a colour photograph of the back of the eye (retina, optic disc, macula, vessels). RFMiD's images.
- **Condition / label**: one of RFMiD's 45 condition codes (e.g. `DR` diabetic retinopathy, `MH` media haze); an image can have several. **Normal** = no condition (`Disease_Risk` = 0); the VLM writes it as `normal`.
- **Frequent conditions**: the 16 with ≥ 20 training images, chosen from training counts only. The headline metric is macro-F1 over them.
- **Deduplicated split**: an official split minus the images with the same eye in an earlier split (`docs/exclusions.json`, found by the vessel-pattern audit; ADR 0001). Deduplicated test = 609 images.
- **Same-eye pair**: two images whose retinal vessels match geometrically (≥ 8 RANSAC inliers). Not the same as a near-identical photo: most same-eye pairs are different photos of the eye.
- **Case**: a training image shown to the VLM with its **recorded findings** (its labels, as a generated "report"). RFMiD has no free-text reports.
- **Report (label-report)**: the deterministic text built from a case's labels and one fixed description per condition (`eye_rag.vlm.case_report`). It carries no information beyond the labels.
- **kNN vote**: predict a label when the cosine-weighted share of the 20 nearest training images carrying it is ≥ 0.20 (M1, chosen on validation).
- **hybrid_knn**: hybrid retrieval (dense image vector + sparse report text, RRF) whose query text is built from the kNN vote's labels. The retrieval behind the VLM arm.
- **Arm**: one way of answering, scored on the same images: `zero_shot` (VLM, photo only), `retrieval` (VLM + 3 cases, true labels), `shuffled` (same cases, wrong labels), `knn_weighted`.
- **Shuffled labels**: each retrieved case shown with the recorded findings of a random other training case, never one of the query's true case label sets (`shuffled_case_labels`). The faithfulness test (ADR 0002).
- **Explanation**: per diagnosed label, a **source** (`image`, `cases`, `both`) and the cited case numbers.
- **Citation check**: the code check on an explanation (labels covered once, cases exist, source agrees with citations, cited case records the label). **Verified** = passed, possibly after retries. Verified means consistent with the text shown, not correct.
- **Injected label**: a label in the shuffled-arm answer that is in the shown (wrong) case text, in none of the true cases, not in the zero-shot answer, and not true for the image.

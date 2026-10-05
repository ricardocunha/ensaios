---
title: "My eye-scan RAG cited its sources. It was reading the labels."
subtitle: "A local vision model with retrieved retinal cases on a public dataset: what retrieval added, a shuffled-labels test that took all of it away, and why a citation check couldn't tell the difference"
platforms: Medium, dev.to, Hashnode
status: DRAFT — numbers final (code/docs/RESULTS.md), dataset facts in code/docs/DATA.md
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-multimodal-medical-rag-eye
---

# My eye-scan RAG cited its sources. It was reading the labels.

> **Research demo, not a medical device.** Nothing here diagnoses anyone or supports a clinical decision. Every number below is agreement with the labels of one public dataset, not diagnostic accuracy on patients.

The pitch for multimodal medical RAG goes like this. A vision-language model looks at a retinal photo. Next to it, you put the most similar photos from a labelled archive, each with its findings. The model diagnoses the new photo, cites the archive cases it relied on, and now its answer is "grounded" and "explainable": a doctor can check the cited cases.

I wanted to know whether that holds up, and how you would tell. So I built one, entirely on a laptop, on a public dataset of 3,200 retinal photos, and compared it with two simpler things: the same model with no retrieved cases, and a plain nearest-neighbour vote over image embeddings. Then I ran the test I think every retrieval-augmented system with explanations should run: keep the retrieved photos, swap their labels for wrong ones, and see what the model does. The idea is project #2 of the video *"5 AI Agents Projects to Build in 2026"*; the architecture, code and numbers here are mine.

The short version:

- **Retrieval helped the model a lot**: macro-F1 over 16 frequent conditions went from 0.058 to 0.298.
- **It still lost to the nearest-neighbour vote it was built on** (0.341), and took 7.5 s per image instead of a vector lookup.
- **With the labels shuffled, the whole gain disappeared** (0.056, the same as no retrieval at all). The model was reading the labels next to the photos, not comparing the photos.
- **An explanation agent with a citation check passed 90 % of explanations with the true labels and 89 % with the shuffled ones.** It verified that the citations matched the text the model was shown. It couldn't tell whether that text was true.

Every number comes from the repo's `docs/RESULTS.md`; the dataset facts and licences are in `docs/DATA.md`.

## Why this matters in Brazil

Brazil has a well-documented ophthalmology dataset: **BRSET**, the Brazilian Multilabel Ophthalmological Dataset (Nakayama et al., *PLOS Digital Health*, 2024). It holds 16,266 fundus photos of 8,524 patients from three ophthalmology centres in São Paulo, 2010–2020, with multi-label disease labels, image-quality fields and demographics. That's five times the images of the dataset I used, from Brazilian patients, with quality labels that would let you test whether retrieval fails on bad photos.

I didn't use it. BRSET is "open" in the PhysioNet sense: **credentialed** access, which means an account, a CITI research-ethics course and a signed data use agreement. That's a reasonable protection for patient data. It's also a real barrier for a reader who wants to rerun an article in an afternoon, and this project doesn't sign up for accounts. So the pipeline runs on a public dataset with no account, and is built so the index can be swapped for BRSET by anyone who has access. BRSET's agreement asks anyone who publishes results to publish their code too; this repo does that anyway.

The point for a Brazilian team is the one this article ends on: whichever dataset you use, the evaluation below is cheap to run, and it's the part that tells you whether "explainable" means anything.

## The setup

```
fundus photo ─► BiomedCLIP image embedding ─► Qdrant (local): dense image vectors + sparse "report" text
                                                  │  hybrid search, Reciprocal Rank Fusion
                                                  ▼
                          3 most similar training cases (photo + recorded findings)
                                                  │
           query photo + 3 cases ─► Qwen3-VL-8B (4-bit, local, mlx-vlm) ─► Diagnosis{labels, cited_cases}
                                                  │
                     explanation agent: per label, source = image | cases | both, cited cases
                                                  │
                     citation check (code, no model): cited cases exist and carry the label
```

Everything runs locally on an M4 Pro: BiomedCLIP for embeddings, Qdrant in local mode, and Qwen3-VL-8B-Instruct in a 4-bit MLX build. The model answers with typed JSON (Pydantic): labels from RFMiD's fixed list of 45 condition codes, or "normal", and nothing else. An invalid answer is sent back with the validation error, up to two retries. Across 1,218 diagnosis calls, none failed.

## The data, and what I had to fix before trusting it

**RFMiD 1.0** (Pachade et al., 2021): 3,200 colour fundus photos from three cameras in India, labelled by two senior retina specialists with 45 conditions plus "any disease", with an official 1,920 / 640 / 640 split. It's CC BY 4.0, and a pinned Hugging Face mirror downloads it with no account. The labels are multi-label and long-tailed: 16 conditions have at least 20 training images, and 29 of the 45 have fewer. So the headline metric is macro-F1 over those 16 frequent conditions, each counting equally.

**Duplicates.** While building the baselines I noticed two test images with a near-identical training photo of the same eye, carrying a *different* label. So I checked every pair of the 3,200 images, all 5.1 million of them. Embedding similarity couldn't do it: 1,587 pairs have cosine ≥ 0.99, and nearly all are different eyes that happen to look alike. Perceptual hashing couldn't either. What worked was matching the retina's vessel pattern geometrically (SIFT keypoints, one-to-one matching, a RANSAC transform that must look like a re-photograph), with thresholds set by looking at pairs side by side.

It found 154 same-eye pairs among 263 images, 70 of them across splits. **31 test images** have the same eye in an earlier split; every number below leaves them out, which leaves 609 test images.

Two surprises came out of that. Removing them didn't change the nearest-neighbour baseline (0.339 → 0.341): BiomedCLIP rarely retrieves the same eye, because a global embedding doesn't key on the vessel pattern. And **the labels disagree with themselves**: 83 of the 154 same-eye pairs (54 %) carry different label sets. Some of that is legitimate, since a different field of view can show a different finding. But among the 8 pairs that are near-identical photos, 7 have different labels. That bounds what any method can score against these labels.

## Baselines: a vector lookup is hard to beat

Before any vision-language model, two baselines on the same embeddings:

| Method (test, 640 images) | macro-F1, 16 frequent |
|---|---|
| predict every label (floor) | 0.108 |
| BiomedCLIP zero-shot (text prompts) | 0.141 |
| **kNN vote**: share of the 20 nearest training images carrying the label ≥ 0.20 | **0.339** |

k and the threshold were chosen on the validation split. Half of the top-10 neighbours share a label with the query, against 15 % at random. kNN does well on conditions with a striking overall look (myopia, optic disc edema, media haze, vein occlusions: F1 0.58–0.68) and badly on small findings a 224-pixel global embedding can't see (drusen, laser scars, disc pallor: 0.00–0.23).

That 0.339 (0.341 without the duplicates) is the number the RAG system has to beat.

## Hybrid retrieval, and a text side that is only labels

The "R" in this RAG is supposed to bring back cases *with their reports*. RFMiD has no reports, only labels. So each training image gets a deterministic "report" built from its labels and one fixed description per condition, for example "diabetic retinopathy (DR): microaneurysms, dot and blot hemorrhages and hard exudates." It contains nothing the labels don't.

The Qdrant index holds both: a dense image vector and a sparse bag-of-words vector of the report, fused with Reciprocal Rank Fusion. The catch is the query side. A new photo has no labels, so its text has to come from something available at test time. I tried two sources:

- **The kNN vote's labels**: the hybrid search then re-ranks towards cases that agree with the dense neighbours. Label precision at 3 went from 0.277 (dense only) to 0.329. I picked this setting for the RAG system, on validation.
- **The vision model's own zero-shot labels**: worse than dense only (0.243). The model called 60 % of test images "media haze" (366 of 609, against 103 true), and the text side dutifully pulled in hazy cases.

Hybrid search is only as good as the text you can honestly put in the query.

## Three arms: retrieval helps the model, and still loses

The model sees the three retrieved photos, each followed by its recorded findings, and then the query photo. Same 609 test images for every arm; intervals are 95 % paired bootstrap over images:

| Arm | macro-F1, 16 frequent (95 % CI) | s / image |
|---|---|---|
| VLM zero-shot | 0.058 (0.042–0.077) | 5.2 |
| **VLM + 3 retrieved cases** | **0.298** (0.249–0.344) | 7.5 |
| kNN vote | 0.341 (0.304–0.380) | < 0.01 |

**The model alone is below the "predict everything" floor.** It names about one finding per image (1.13 on average), and that finding is usually media haze.

**Retrieved cases add 0.24 macro-F1**, and the paired difference is clearly real (+0.187 to +0.286). Diabetic retinopathy goes from 0.18 to 0.58, myopia from 0.04 to 0.46.

**But the result is not better than the kNN vote that chose the cases.** The paired difference is −0.043 (−0.084 to −0.006): probably slightly worse, certainly not better. The model wins only on a few rare conditions where kNN's threshold never fires (central serous retinopathy, chorioretinitis, laser scars), on 10–12 positive images each.

And in 74 % of its answers, every label the model gave appears in one of the three cases it was shown. That's either a model that compares photos well, or a model that copies the findings next to the photos. The two look the same on this table.

## The test: same photos, wrong labels

So I ran the retrieval arm again on the same 609 images, with the same three retrieved photos for each, and one change: each case was shown with the recorded findings of a different, random training case. It's never one of the query's real case label sets, and it's seeded per image, so the run is reproducible. A model that compares photos should barely move. A model that reads labels should follow the new text.

| Arm (same 609 images) | macro-F1, 16 frequent (95 % CI) |
|---|---|
| VLM zero-shot | 0.058 (0.042–0.077) |
| VLM + cases, true labels | 0.298 (0.249–0.344) |
| VLM + cases, **shuffled labels** | **0.056** (0.044–0.069) |

**Shuffling the labels erased the entire retrieval gain.** With the same photos and wrong labels, the arm is indistinguishable from no retrieval at all (difference −0.002, CI −0.023 to +0.016). The true-versus-shuffled gap (+0.243) is the same size as the whole retrieval gain (+0.240). The three case photographs, on their own, added nothing measurable.

**58 % of answers changed** when only the text changed. And the new answers followed it: in 29 % of images (205 labels in total), the model gave a label that was in the shuffled text, in none of the real cases, not in its own zero-shot answer, and not true for the image. Nothing but the wrong text explains those labels.

## The explanation agent, and a check that passes either way

The plan always included an explanation step, because "it cites its sources" is most of the pitch. The diagnosis itself already has a `cited_cases` field, and it looks clean: 65 % of answers cite a case, none cite a case that doesn't exist, and in 90 % of citing answers every cited case shares a label with the answer.

The explanation agent goes further. For each diagnosed label, the model must say whether it comes from the photo (`image`), from the cases (`cases`) or `both`, and cite the case numbers. Then code, not a model, checks four things:

1. Every diagnosed label is explained exactly once, and nothing else is.
2. Every cited case exists.
3. The source agrees with the citations: "image" cites none, "cases" or "both" cite some.
4. **Every cited case's recorded findings contain the label it is cited for.**

A failed check goes back to the model as a list of problems, up to two retries. An answer that still fails is kept and marked unverified. I ran it on both the true-label and the shuffled-label diagnoses:

| | true labels | shuffled labels |
|---|---|---|
| verified by the check (95 % CI) | 90.0 % (87.5–92.3) | 89.3 % (86.9–91.8) |
| verified case citations naming a label the image really has | **48.8 %** (of 549) | **12.2 %** (of 344) |
| verified findings that say "I see it in the photo", no case | 28 % | 49 % |

**The check passed as often with wrong labels as with right ones.** It did its job: on the first try, the most common problem was a case cited for a label it doesn't carry (296 times with true labels, 520 shuffled), and feedback fixed most of them. But its job was consistency with the text shown, and the text was wrong.

**A verified citation is not a correct one.** Even with the true labels, fewer than half of the verified case citations name a label the image has. With shuffled labels, one in eight.

**And the explanations claim the photo.** Nearly every cited finding is sourced "both", seen in the photo *and* in the cases. With shuffled labels, half say "photo only". We know from the previous section that the answers moved with the text, so "I can see it in the image" is not evidence that the model did.

Here is one case, picked from the shuffled run, first try, verified (test image 205). The image is labelled diabetic retinopathy. Its three real nearest cases are all diabetic retinopathy, and with them the model answered diabetic retinopathy. Shown the same three photos, with case 1 relabelled as age-related macular degeneration and cases 2 and 3 as normal, it answered macular degeneration, cited case 1, sourced it "both", and explained:

> "The QUERY photograph shows signs of age-related macular degeneration, consistent with the finding in reference case 1, which was also labeled ARMD."

Every check passed.

Some of the explanations the check rejected are just as telling. In one validation case, asked why it cited three myopia cases for tessellation, which none of them carried, the model kept the citation through every retry, because tessellation "is associated with" myopia. I left the prompt as it was: tuning it until the check passes would have measured my prompt, not the system.

## What 609 images can and can't tell you

The intervals above cover one kind of uncertainty: which test images happened to be drawn. They don't cover a different model, prompt, number of cases or dataset. This is one dataset (three cameras, one hospital network in India), one 8B model at 4 bits, one prompt and greedy decoding. A stronger model might compare photos better, and the shuffled-labels test is exactly how you'd find out.

The reference is RFMiD's labels, and they disagree with themselves on the same eye. Camera is not in the label files, so I couldn't test whether kNN, and so the cases the model sees, partly matches cameras instead of disease. None of this is diagnostic accuracy.

## What I'd tell a team building this

1. **Run a shuffled-labels test before you call anything "grounded".** Keep the retrieved images, replace their labels, and score again. It costs one more run. If the score falls to the zero-shot level, your model is reading the labels and the retrieved images are decoration. Here it took every point of the gain.
2. **Compare with the nearest-neighbour vote, not only with the model alone.** "Retrieval improves the VLM by 0.24" is true and misleading. The vote over the same retrieved cases was at least as good, in milliseconds, with no model at all.
3. **A citation check proves consistency, not correctness.** Check citations in code, because it catches real mistakes (here, a case cited for a label it doesn't carry, hundreds of times). Then measure separately whether the cited claims are true. Here they were true for 49 % of verified citations, and for 12 % when the labels were wrong, with the same pass rate.
4. **Don't trust "I see it in the image".** A model's account of where its answer came from is a generated sentence like any other. Test it by changing what it could have used, and watch what moves.
5. **Audit your duplicates and your labels before your model.** The vessel-pattern audit took about 11 minutes of compute, plus looking at pairs by eye to set its threshold, and found 154 same-eye pairs. Half of them disagree on the labels. That ceiling applies to every method you'll ever compare on this dataset.
6. **For a Brazilian dataset like BRSET, the harness is the reusable part.** Swap the index, keep the three arms, the shuffled-labels run and the bootstrap. Whoever has credentialed access can run the same test on their own hardware and find out whether retrieval helps their model look, or just helps it read.

---

*Idea from the video "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (project #2, multimodal medical RAG for eye disease). Data: RFMiD 1.0, S. Pachade et al., "Retinal Fundus Multi-Disease Image Dataset (RFMiD): A Dataset for Multi-Disease Detection Research", Data 2021, 6(2), 14, doi:10.3390/data6020014, CC BY 4.0. Models: BiomedCLIP (Zhang et al., 2023, MIT, research use only) and Qwen3-VL-8B-Instruct (Apache-2.0), both run locally. BRSET: Nakayama et al., PLOS Digital Health, 2024 (PhysioNet). Not a medical device. Code, tests and every number: [github.com/ricardocunha/ensaios › articles/2027-01-multimodal-medical-rag-eye](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-01-multimodal-medical-rag-eye).*

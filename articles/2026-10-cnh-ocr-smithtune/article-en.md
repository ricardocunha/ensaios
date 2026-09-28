---
title: "I tested LangSmith's brand-new smithtune on Brazilian driver's licenses. Here's what it can and can't do"
subtitle: "Fine-tuning open OCR models for the CNH, and distilling a Claude agent into a 9B model, in the first week of smithtune"
platforms: Medium, dev.to, Hashnode
status: DRAFT — replace every [[RESULT: …]] before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-cnh-ocr-smithtune
---

# I tested LangSmith's brand-new smithtune on Brazilian driver's licenses. Here's what it can and can't do

On September 24, 2026, LangChain released **LangSmith Fine-Tuning** and its CLI, **smithtune**. The promise: take the traces your agent already produces in LangSmith, turn the good ones into a training set, fine-tune an open model on managed GPUs, evaluate it against the original, and deploy it. All from one CLI, without provisioning a single GPU.

I wanted to try it on a problem I care about: **reading Brazilian driver's licenses (CNH)**. Fintechs, car-rental apps, delivery platforms: half of Brazil's onboarding flows start with "take a photo of your CNH." Frontier APIs handle this well, but they are expensive per document, and they send personal data out of the country, which is a real LGPD conversation.

Two days after launch, this is a field report, not a tutorial. There's plenty of code (the repo is linked at the end), and one early finding changed the whole design.

---

## What smithtune actually is

In plain terms, smithtune is **a pipeline from "my agent's history" to "a smaller model that behaves like my agent."** It has four stages:

1. **Curate.** `smithtune dataset pull` downloads *trajectories* from a LangSmith tracing project. A trajectory is one complete agent run: the user message, every model turn and every tool call, up to the final answer. You select them with a LangSmith filter, for example "only runs whose `correctness` feedback is 1". Optionally, `smithtune dataset triage` sends each one to an **agent council**: several LLM judges that score it against a rubric *you* write. There's no default rubric, and the tool refuses to guess. Then `dataset push` stores the curated set back in LangSmith.
2. **Prepare and train.** `smithtune prepare` renders every trajectory into the exact chat template of the target model (tokenizer revision pinned, template verified) and splits the data about 80/10/10. `smithtune train` runs **LoRA supervised fine-tuning** on a managed provider: **Fireworks** or **Baseten**.
3. **Evaluate.** This is the clever part. `smithtune evaluate` runs a **replay evaluation**. For each step of a held-out trajectory, it gives the model the recorded context and asks it to predict the next action. Tool calls are *not* executed, so nothing touches your production systems. An LLM judge scores whether the prediction agrees with what the original model did, and the base and fine-tuned models are compared side by side as LangSmith experiments.
4. **Deploy.** `smithtune deploy` puts the tuned model behind an endpoint, and `smithtune undeploy` tears it down.

Every step that costs money requires `--confirm`; without it, smithtune only prints a preview. I appreciated that more than I expected.

LangChain's launch post reports a Kimi K3 fine-tune reaching a 96.0 task score, against 90.0 for the base model and 87.0 for GPT-5.6, on one of their internal agents. That's the pitch: **your traces are a dataset you're already paying for.**

## The catch I found on day one

My original plan was simple: fine-tune a state-of-the-art OCR model, Datalab's **Chandra**, on CNH images using smithtune.

Then I read the source. Two things stand out in v0.1.0:

**1. Trajectories that contain images are filtered out.** Not by accident. There's a dedicated function, `multimodal_types()`, that looks for `image`, `image_url`, `input_image`, audio, video, files and PDFs. Triage then drops those trajectories before judging:

```python
# smithtune/triage.py (v0.1.0)
"reason": "Filtered before judging: multimodal content (" + ", ".join(media) + ")."
```

**2. The base models come from a fixed list.** On Fireworks: Qwen3.8-27B, Kimi K3, DeepSeek V4 Flash and Muse Glimmer 30B. On Baseten: Qwen3.8-27B, Qwen3.5-9B, Kimi K3 and GLM-5.3-Flash. Each has a pinned tokenizer revision and a hand-written "renderer" that reproduces its chat template exactly. That's also why you can't just point it at any Hugging Face model: training on a template that differs from the one used at inference quietly degrades the model, and smithtune chose correctness over breadth.

So **smithtune can't fine-tune an OCR model today.** That isn't a flaw. It's a text-and-tool-calls product in public beta. But it changes the architecture.

## The architecture that works: Reader + Extractor

I split the problem at the point where pixels become text:

```
CNH photo ─► [ Reader ] ─► Transcription ─► [ Extractor ] ─► CNH Record (validated JSON)
             vision OCR model                 text-only agent with tools
             fine-tuned with HF / MLX         Claude Sonnet 5 → Qwen3.5-9B via smithtune
```

- The **Reader** is a vision model that turns the photo into a *Transcription*: one `LABEL: value` line per printed field, **exactly as printed, errors included**. It never validates anything.
- The **Extractor** is a text-only agent. It reads the Transcription and calls deterministic tools: CPF check digits, CNH-number check digits, a "suggest OCR fixes" tool that tries `O→0`, `S→5`, `B→8`, date normalization, and consistency checks such as "a CNH issued at 45 is valid for 10 years" (Lei 14.071/2020). It ends by submitting a validated **CNH Record**, or by rejecting the input if it isn't a CNH.

The Extractor is exactly the kind of agent smithtune was built for: multi-step, tool-heavy, cheap to verify. And because it never sees pixels, its trajectories pass smithtune's filter.

## Stage 1: three open OCR models, one fine-tuned on a MacBook

I started from Hugging Face's excellent overview of open OCR models ([Supercharge your OCR pipelines with open models](https://huggingface.co/blog/ocr-open-models)) and picked three models that span the design space:

| Model | Size | Why |
|---|---|---|
| **Chandra 2** (`datalab-to/chandra-ocr-2`) | ~5B | OCR specialist. Its model card reports **95.2% on Portuguese** (Chandra 1: 84.3%) |
| **PaddleOCR-VL-1.6** | 0.9B | A tiny specialist, 109 languages, Apache-2.0 |
| **Qwen3.5-9B** | 9B | A generalist, and the *same base model* as my smithtune Student |

A licensing note, because it will bite someone: **Chandra 2's weights are not free for most companies to use commercially.** The license (a modified OpenRAIL-M) prohibits commercial use by organizations with more than US$2M in revenue *or* funding, and a share-alike clause covers derivatives *and outputs*. "Open weights" isn't the same as "free to use at work." Read the license.

**Data: synthetic only.** I will not train on real people's documents, and neither should you. I wrote a generator that:
- creates consistent fake people with Faker `pt_BR`, with **valid CPF and CNH check digits** so the checksum tools have something real to verify;
- renders a CNH-*inspired* card (same labels, similar layout, no national emblems, no security features, and a big *AMOSTRA / SYNTHETIC* watermark), plus a CNH Digital screenshot variant;
- degrades each card into a "phone photo": perspective, rotation, shadows, blur, JPEG artifacts;
- mixes in 10% decoys (RG-like cards, invoices) that the pipeline must reject.

That gives 2,293 training images (I planned 3,000; an interrupted run made me settle, and it's plenty for LoRA), 300 for validation, 300 for test, and 100 "hard" images. To check realism beyond my own renderer, I also evaluate on the **BID Dataset** (Soares et al., SIBGRAPI 2020), cited and not redistributed. More on that below, because it changed the story.

**Training runs locally.** `mlx-vlm` supports LoRA on Apple Silicon for PaddleOCR-VL and for the Qwen3.5 family, which Chandra 2 is built on. I fine-tuned only the smallest model, PaddleOCR-VL (0.9B). It trains in under two hours on an M4 Pro with 48 GB, which let me run two full rounds and learn something from each. Chandra 2 and Qwen3.5-9B appear below zero-shot only; fine-tuning them with 4-bit QLoRA is the obvious next experiment:

```bash
python -m mlx_vlm.lora --model-path PaddlePaddle/PaddleOCR-VL-1.6 --dataset data/synth \
  --epochs 1 --lora-rank 32 --grad-checkpoint --train-on-completions
```

### Zero-shot: the generalist wins, and the specialists won't follow instructions

Before fine-tuning anything, I gave all three models the same instruction: *"transcribe this CNH as one `LABEL: value` line per printed field, exactly as printed; if it isn't a CNH, answer `NÃO É CNH`."* I tested them on 50 held-out synthetic images (43 CNHs and 7 decoys), with Qwen's thinking mode off.

| Model (zero-shot) | Label accuracy | Value recall | CER | Decoys rejected | s / image (M4 Pro) |
|---|---|---|---|---|---|
| **Qwen3.5-9B** (generalist) | **72.4%** | 99.8% | 0.31 | 3/7 | 21.3 |
| Chandra 2 (~5B)* | 17.3% | **100.0%** | 6.50 | 0/7 | 51.0 |
| PaddleOCR-VL-1.6 (0.9B) | 17.4% | 85.5% | 2.43 | 0/7 | 3.1 |

The accuracy metrics are measured on the CNHs only, and decoys are counted separately:
- *Label accuracy* is the share of fields whose value landed under the right label, exactly. The label itself is matched loosely: `CAT.HAB.` counts as `CAT. HAB.`.
- *Value recall* ignores format: is each printed value *somewhere* in the output?
- *CER* is the character error rate against the reference Transcription. Above 1.0 means more edits than the reference has characters.

<sub>*Chandra 2 got a 3,000-token output budget. At 600, 46 of 50 outputs were cut off mid-card. About 14% label accuracy is the floor: blank fields such as PERMISSÃO and ACC match even when the format is ignored.</sub>

Three things surprised me:

- **The specialists read perfectly, but won't take instructions.** Chandra 2 found *every* printed value (100% recall), then ignored the prompt and wrote its own HTML layout format, with a bounding box on every element:

  ```html
  <div data-bbox="335 284 556 320" data-label="Text"><p><b>ASAFE COSTA SIQUEIRA</b></p></div>
  ```

  That's great for document pipelines. It's just not what I asked for, and at 51 s per image the HTML costs more tokens than the text it carries. PaddleOCR-VL writes free text: multi-column rows come out as `Nº REGISTRO VALIDADE 1º HABILITAÇÃO 34627740679 12/10/2027 02/11/2009`, and the label–value pairing is gone. It also loops and repeats blocks, hence a CER above 2.

- **The generalist's errors are the dangerous kind.** Qwen3.5-9B follows the format for 35 of 43 CNHs; on the other 8 it switches to "label on one line, value on the next." Worse, it sometimes writes a *well-formed, wrong* date: `DATA NASCIMENTO: 29/05/1990` when the card says `23/07/1990`. A checksum catches a misread CPF; nothing catches a plausible date. That's a big part of why the Extractor exists.

- **Nobody rejects the decoys.** Of 7 non-CNH images, Qwen said "not a CNH" 3 times, and the specialists never did.

The zero-shot results make the case for fine-tuning: the knowledge is there (value recall up to 100%), but the output contract isn't. That should be the easiest thing to teach with LoRA.

### Fine-tuning: 99.8%, on my own cards

I started with the smallest model, PaddleOCR-VL (0.9B): LoRA rank 32, one epoch over 2,293 images. It took **1h51 on the M4 Pro, peaking at 5.7 GB**.

Getting there took one detour. My first run died with a Metal out-of-memory error, and the log said `trainable params: 451M || all params: 905M (49.8%)`, which is not what LoRA looks like. mlx-vlm freezes vision encoders by attribute name (`vision_model`, `vision_tower`, …), and PaddleOCR-VL calls its encoder `visual`, so the whole vision tower was being trained. Freezing `visual` myself brought it down to 12.1M trainable parameters (1.3%). Lesson: **always read the trainable-parameter line.**

| PaddleOCR-VL, synthetic test | Label accuracy | Value recall | CER | Decoys rejected | s / image |
|---|---|---|---|---|---|
| zero-shot | 17.4% | 85.5% | 2.43 | 0/7 | 3.1 |
| **+ LoRA** | **99.8%** | **99.8%** | **0.00** | **7/7** | **2.8** |
| + LoRA, 100 degraded "hard" images | 99.8% | 99.8% | 0.00 | 11/11 | 2.8 |

The test images share no CPFs, no names and no transcriptions with training. The only error in the test set is a lost accent (`CÂMARA` → `CAMARA`) on a CNH Digital screenshot. A 0.9B model on a laptop beats zero-shot Qwen3.5-9B by 27 points at 7× the speed.

I was ready to write "fine-tuning solved it." Then I tested it on real cards.

### Then I tested it on real cards

The **BID Dataset** gives me what my renderer can't: **real CNH card designs, scanned**, with synthetic personal data and blurred faces, often **sideways or upside down**. I used the public sample: 70 CNHs (front and open card) and 72 RG/CPF fronts as decoys. Its annotations are text boxes rather than labelled fields, so I pair each value with its label by format and position, and score the 7–9 fields that can be paired unambiguously.

| BID (real card designs) | Label accuracy | Value recall | Real CNHs **rejected** | RG/CPF rejected | s / image |
|---|---|---|---|---|---|
| PaddleOCR-VL zero-shot | 0.0% | 80.8% | 0/70 | 0/72 | 1.2 |
| **PaddleOCR-VL + LoRA** | 32.0% | 34.0% | **48/70** | 72/72 | 0.6 |
| Qwen3.5-9B zero-shot | **48.2%** | **85.4%** | 5/70 | 59/72 | 7.1 |

From 99.8% on my cards to 32.0% on real ones. The fine-tuned model **answered "NÃO É CNH" for 48 of 70 genuine driver's licenses.**

Here's the interesting part. On the 22 real CNHs it *did* accept, it scored **92.9% label accuracy and 96.3% value recall**. The reading skill transferred. What didn't transfer was its idea of *what a CNH looks like*. My generator had one design, so the model learned "CNH = that design" and treated everything else as a decoy. Two more clues:

- **Stopping earlier doesn't help.** By step 1,000 the model is already at 99.9% on synthetic data and still rejects 49 of 70 real CNHs. At step 200 it rejects nearly everything, synthetic included. The problem is in the data, not the schedule.
- **My decoys were unrealistic too.** Zero-shot Qwen rejects 59 of 72 *real* RG and CPF cards, but only 3 of 7 of my synthetic decoys: invoices, letters and a lavender "REGISTRO GERAL" card that look like nothing real.

This is the sim-to-real gap in its purest form, and a synthetic test set will never show it to you. **If you fine-tune on synthetic documents, you need at least a small real evaluation set**, even one you can't train on.

### Round 2: vary what shouldn't matter

The fix is *domain randomization*: vary everything that shouldn't affect the answer, so the model can't use it as a shortcut. With the same model, hyperparameters and 2,293-image budget, I changed only the data:
- **Design:** six palettes, three font families, jittered layouts, boxed fields, labels above or below the box, and printed label variants (`CAT.HAB.`, `N° REGISTRO`, `1º HABILITAÇÃO`).
- **Capture:** 40% flatbed scans, and a quarter of images turned 90°, 180° or 270°.
- **Decoys:** RG and CPF cards in the *same* palettes and boxed style.

To keep BID honest as a test set, I used only coarse properties I'd noticed while writing its loader, and I evaluate on it once per round.

| BID (70 real CNHs, 72 RG/CPF) | Label accuracy | Value recall | Real CNHs rejected | RG/CPF rejected | s / image |
|---|---|---|---|---|---|
| PaddleOCR-VL + LoRA, round 1 (one design) | 32.0% | 34.0% | 48/70 | 72/72 | 0.6 |
| **PaddleOCR-VL + LoRA, round 2 (randomized)** | **52.3%** | 60.6% | **30/70** | **72/72** | **0.9** |
| Qwen3.5-9B zero-shot | 48.2% | 85.4% | 5/70 | 59/72 | 7.1 |

And it cost nothing at home: on my original synthetic test set the round 2 model still scores **99.8%** (hard set: 99.7%, versus 99.8% in round 1), with every decoy rejected.

Same model, same hyperparameters, same 2,293 images; only the variety changed. Label accuracy on real cards rose **20 points**, and wrongly rejected CNHs dropped from 48 to 30, while real RG and CPF cards were still rejected 72 out of 72. The 0.9B model now edges past zero-shot Qwen3.5-9B (52.3% vs 48.2%) at about **8× the speed**.

It is not solved, though. It still turns away **30 of 70 real CNHs**. On the 40 it accepts it reads 78.8% of labels and 91.8% of values; the newly accepted cards are harder ones, so the average on accepted cards fell from 92.9%. Qwen, meanwhile, rejects almost no real CNH (5/70). It just reads less precisely.

Two lessons I'll take into the next project:

- **Variety beats volume.** I didn't add a single image; I made the same 2,293 images less alike. That alone moved real-world accuracy by 20 points.
- **The gate is the hard part, and it may not belong in the vision model.** A model fine-tuned on one narrow distribution becomes very confident about what's "in" and very quick to reject what's "out". In this pipeline the Extractor sees every Transcription anyway, and zero-shot Qwen rejected real RG/CPF cards well (59/72) without any training. So round 3 tests exactly that.

### Round 3: take the decision away from the vision model

The Reader now gets a plain instruction, "transcribe this document", with no refusal option. Decoys are trained on what they actually print: an RG becomes `NOME: … / FILIAÇÃO: … / NATURALIDADE: …`. The CNH-or-not decision moves to the text side. In the full pipeline the Extractor makes it; for this measurement a simple rule stands in: a Transcription is a CNH if it carries at least two labels that only a CNH prints (CAT. HAB., Nº REGISTRO, 1ª HABILITAÇÃO, VALIDADE, PERMISSÃO, ACC). The images, model, hyperparameters and 2,293-image budget are the same as round 2.

| BID (70 real CNHs, 72 RG/CPF) | Label accuracy | Value recall | Real CNHs rejected | RG/CPF rejected | s / image |
|---|---|---|---|---|---|
| Round 1: one design, Reader decides | 32.0% | 34.0% | 48/70 | 72/72 | 0.6 |
| Round 2: randomized, Reader decides | 52.3% | 60.6% | 30/70 | 72/72 | 0.9 |
| **Round 3: randomized, text decides** | **81.0%** | **94.4%** | **0/70** | 64/72 | 2.3 |
| Qwen3.5-9B zero-shot | 48.2% | 85.4% | 5/70 | 59/72 | 7.1 |

**Not a single real CNH rejected**, and accuracy on real cards went from 32% to 81% across the three rounds. On my synthetic sets nothing got worse (100% on the test set, 99.6% on the hard set). A 0.9B model on a laptop now beats zero-shot Qwen3.5-9B on real cards by 33 points, at three times the speed.

The trade-off is visible too: **8 of 72 real RG cards slipped through the gate.** All 8 are the same RG design, and on them the Reader starts repeating CNH labels with *empty* values (`Nº REGISTRO:`, `PERMISSÃO:`), a habit learned from thousands of CNHs, while the rule only checks that the labels exist. The fix is obvious: count only CNH labels that carry a plausible value (an 11-digit registration number, a valid category, a date). But I designed that fix after looking at BID's failures, so a new BID score would no longer be an honest test, and I'm leaving it as the next step. In the full pipeline, those 8 would also have to get past the Extractor, which validates checksums before submitting anything.

What I'll take away from Stage 1:

- **Synthetic scores can't tell good from bad.** All three rounds score 99–100% on my synthetic sets. Only the real set separates them: 32%, 52%, 81%.
- **Let the vision model read, and decide elsewhere.** The biggest jump didn't come from more data or a bigger model; it came from taking one decision away from the part of the system that couldn't generalize it.

## Stage 2: distilling a Claude agent with smithtune

### Recording the Teacher

The Extractor is a LangChain `create_agent` with eight tools. The Teacher is **Claude Sonnet 5**. I ran it on 1,500 Transcriptions: real Reader output plus ground-truth Transcriptions with **injected OCR noise** (letter/digit swaps, broken date separators, `A8` instead of `AB`, dropped lines). Clean inputs don't teach error recovery.

Here's the most useful trick: **because the data is synthetic, every run has ground truth.** So the runner scores each trajectory field by field and writes the score back to LangSmith as feedback (`field_accuracy`, `exact`). That gives smithtune a *trusted* quality signal to filter on, which its own documentation recommends over "no errors" or "the agent finished":

```bash
smithtune dataset pull runs/smithtune/golden --project-id $PROJECT \
  --filter 'and(eq(feedback_key, "exact"), eq(feedback_score, 1))' \
  --target-count 1000 --no-triage
```

`[[RESULT: how many of 1,500 Teacher runs were exact; Teacher cost]]`

### Does the agent council agree with ground truth?

Since I had ground truth anyway, I ran an experiment no one could run on day two: I ran **council triage** on 200 trajectories with my rubric ("validated checksums before submitting", "never invented a missing field", …) and compared its keep/drop verdicts with the truth.

`[[RESULT: agreement %, false keeps, false drops, one example of a council mistake]]`

### Training, replay evaluation, deploy

```bash
smithtune prepare --provider baseten --model Qwen/Qwen3.5-9B --dataset-id $GOLDEN ...
smithtune plan    --provider baseten --data-dir runs/smithtune/golden --evaluate
smithtune train   --provider baseten --data-dir runs/smithtune/golden --run-dir runs/... --evaluate --confirm
```

`[[RESULT: plan estimate vs actual time/cost; anything that broke]]`

`[[RESULT: replay eval: teacher_agreement base vs tuned]]`

## The numbers that matter

Replay agreement tells you whether the Student *imitates* the Teacher. The business question is different: **does it extract the right CPF?** So I deployed the Student and ran it on the same 300 held-out test Transcriptions as the Teacher:

`[[RESULT: table: Teacher (Sonnet 5) vs base Qwen3.5-9B vs tuned Qwen3.5-9B. Field accuracy, exact records, avg tool calls, p50 latency, $/1k CNHs]]`

`[[RESULT: headline sentence: "the tuned 9B reaches X% of the Teacher's field accuracy at Y% of the cost"]]`

## Verdict on smithtune (v0.1.0)

**What I liked**
- **The right abstraction.** "Traces → curated dataset → LoRA → replay eval → deploy" is the loop teams keep rebuilding by hand.
- **Replay evaluation** is a smart, safe default: it compares models step by step without running tools against real systems.
- **Careful engineering:** pinned tokenizers, verified chat templates, `--confirm` on every paid step, and no default rubric.
- **It's built to be driven by a coding agent:** it ships as a skill (`npx skills add langchain-ai/smithtune`), and the docs read like instructions for one.

**What to know before you start**
- **Text and tool calls only.** Vision, audio and document traces are filtered out.
- **A fixed model list** on two providers. You can't bring your own Hugging Face model.
- **Replay agreement is not task accuracy.** Measure your real metric too.
- **Deployments cost money until you undeploy.** Set a reminder.
- It's a public beta that shipped this week. Expect sharp edges. `[[RESULT: link any issues I opened]]`

**Who should use it today?** Teams that already trace a working agent in LangSmith, pay frontier-model prices for it, and want a cheaper, faster model that behaves the same. If that's you, the path from traces to a tuned model has never been shorter.

**What I'd love in v0.2:** multimodal trajectories. Fireworks can already fine-tune Qwen3-VL-8B on images through its own API. The moment smithtune supports that, a one-stage image→JSON Student becomes possible, and I'll rerun this experiment.

---

**Code, data and adapters:** [github.com/ricardocunha/ensaios › articles/2026-10-cnh-ocr-smithtune](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-cnh-ocr-smithtune) · Synthetic dataset: `[[RESULT: HF dataset URL]]`

*All documents in this project are synthetic. No real person's data was used for training.*

#MachineLearning #LLM #FineTuning #OCR #LangChain #OpenSource #Brazil

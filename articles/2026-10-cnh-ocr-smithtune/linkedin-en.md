<!-- LinkedIn post (EN). ~1,300 chars. Attach the carousel (see carousel outline below). -->

LangChain shipped smithtune two days ago. I pointed it at Brazilian driver's licenses. 🇧🇷🪪

smithtune turns your agent's LangSmith traces into a fine-tuned open model: curate → LoRA on Fireworks/Baseten → replay eval → deploy, all from one CLI.

My plan was to fine-tune an OCR model with it. Then I read the source:
→ v0.1 filters out every trace that contains an image
→ base models come from a fixed list (Qwen, Kimi, DeepSeek, GLM)

So I split the problem in two:
1️⃣ Reader: 3 open OCR models (Chandra 2, PaddleOCR-VL, Qwen3.5-9B) compared zero-shot; the 0.9B one LoRA-tuned on synthetic CNHs, on a MacBook
2️⃣ Extractor: a tool-using agent (checksums, OCR fixes, date rules). Claude Sonnet 5 as Teacher, distilled with smithtune into Qwen3.5-9B

Results:
📉 A 0.9B OCR model fine-tuned on a MacBook: 99.8% on my synthetic cards, then rejected 48 of 70 REAL CNHs as "not a CNH". Synthetic data taught it to read, and also what a CNH "looks like". 🔁 Round 2: same 2,293 images, just more varied (designs, scans, rotations) → +20 points on real cards, now ahead of zero-shot Qwen3.5-9B at 8× the speed. Round 3: let the vision model only read, and decide "is this a CNH?" from the text → 81% on real cards, 0/70 wrongly rejected. The biggest jump came from moving one decision, not from more data.
[[RESULT: 1 line Student vs Teacher, cost]]

Bonus: I measured how often smithtune's "agent council" agrees with ground truth → [[RESULT: %]]

Full write-up + code (100% synthetic data, no real documents) 👇
[[LINK]]

#AI #MachineLearning #LLM #OCR #FineTuning #LangChain #OpenSource

---
Carousel (8 slides):
1. "I tested smithtune on Brazilian CNHs" + synthetic CNH image
2. What smithtune is: 4-step diagram (curate → train → replay eval → deploy)
3. The catch: `multimodal_types()` code snippet + fixed model list
4. Architecture: Reader → Transcription → Extractor
5. Stage 1 results chart (zero-shot vs LoRA, 3 models)
6. Council vs ground truth
7. Teacher vs Student: accuracy vs cost chart
8. Verdict: 4 pros / 4 cons + repo link

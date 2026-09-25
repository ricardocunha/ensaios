# Split extraction into a vision Reader and a text-only Extractor

smithtune v0.1.0 filters out every trajectory that contains images or documents (`triage_source.py::multimodal_types`), and it can only train a fixed allowlist of text LLMs. Chandra and the other OCR models therefore can't be trained with it. We split the system in two. A vision **Reader** is fine-tuned with HF TRL / mlx-vlm LoRA and produces a Transcription. A text-only, tool-using **Extractor** is distilled from a frontier Teacher into a Qwen3.5-9B Student with smithtune on Baseten.

## Considered Options

- **Single end-to-end VLM (image → JSON)**: simpler, but smithtune can't take part at all, and testing smithtune is the main goal.
- **smithtune only, off-the-shelf OCR**: loses the OCR fine-tuning story. We keep it as the fallback if time runs short.

## Consequences

The Transcription is the contract between the two stages. The Reader must not validate or normalize, and the Extractor must never see pixels. When smithtune adds multimodal support, revisit this decision.

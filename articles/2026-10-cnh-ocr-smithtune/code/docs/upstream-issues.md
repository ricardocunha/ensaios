# Upstream issue drafts (not filed)

These are drafts for review, to be filed from the author's GitHub account if approved. Each was reproduced in this project; the versions are in each report.

---

## 1. langchain-ai/smithtune: replay eval marks tool calls invalid when `arguments` is an object; failed cases give no reason

**Title:** Replay evaluation: tool-call `arguments` returned as a dict are scored `arguments_json_valid=false`; failed cases aren't explained

**Environment:** smithtune 0.1.0 (main @ 97fe916), `--provider fireworks`, base `qwen3p8-27b`, judge `accounts/fireworks/models/deepseek-v4p1-flash`, macOS / Python 3.12.

**What happened.** On a tool-calling agent (8 tools), `train --evaluate` produced replay results where, in 32 of 35 tool-call cases, **both the base and the tuned model** were judged *"Candidate tool calls violate the tools available at this assistant turn."* The deterministic metrics show `tool_name_match: true` but `arguments_json_valid: false` and `arguments_schema_valid: false`. The candidates had called the right tools with sensible values.

The Fireworks sampler returned candidates like:

```json
{"function": {"name": "validate_cpf", "arguments": {"cpf": "743.401.179-35"}}}
```

In `evaluation/replay.py` (about lines 384–392), arguments are parsed only when they're a `str`:

```python
if isinstance(raw_arguments, str):
    parsed_arguments = json.loads(raw_arguments); arguments_json_valid = True
```

So an already-parsed `dict` is always "invalid", the schema checks fail, and the judge's verdict follows.

**Suggested fix.** Treat a `dict` as already parsed (`parsed_arguments = raw_arguments; arguments_json_valid = True`), or normalize sampler output to the OpenAI wire format (a JSON string) before scoring.

**Second, related problem.** The same run ended with `evaluation interrupted: 63 cases failed; 45/108 saved; rerun to resume`. The exception is chained (`from errors[0]`), but the CLI prints only the count, so the user can't tell a billing or quota error from a bug. In this case the account's credit had been exhausted. Printing the first error's type and message (and saving failures to a file) would make this diagnosable.

---

## 2. ml-explore/mlx-lm: `mlx_lm.server --adapter-path` is ignored

**Title:** server: `--adapter-path` is silently ignored (adapter looked up with the remapped model path)

**Environment:** mlx-lm 0.31.3, macOS (Apple M4 Pro), Python 3.12.

**Repro.**
```bash
python -m mlx_lm server --model <base> --adapter-path <lora_dir> --port 8088
# request with "model": "<base>" (or omitted): responses equal the base model's
```

In our evaluation, 100 of 100 agent runs gave outcomes identical to the base model. Passing `"adapters": "<lora_dir>"` in the request body does apply the adapter (outputs change).

**Cause.** In `ModelProvider.load`:

```python
model_path = self._model_map.get(model_path, model_path)      # "default_model" -> real path
adapter_path = self._adapter_map.get(model_path, adapter_path) # looked up with the REAL path
```

`_adapter_map` is keyed by `"default_model"`, but the lookup uses the already-remapped `model_path`, so it misses and `adapter_path` stays `None`.

**Suggested fix.** Look up the adapter (and draft model) with the original key before remapping `model_path`.

---

## 3. Blaizzy/mlx-vlm: LoRA doesn't freeze PaddleOCR-VL's vision tower (`visual`); batch size > 1 crashes

**Title:** LoRA on PaddleOCR-VL trains the whole vision tower (`visual` not frozen) and fails with batch_size > 1

**Environment:** mlx-vlm 0.7.3, model `PaddlePaddle/PaddleOCR-VL-1.6`, macOS (Apple M4 Pro, 48 GB), Python 3.12.

**1) Vision tower not frozen.** `python -m mlx_vlm.lora --model-path PaddlePaddle/PaddleOCR-VL-1.6 …` reports `trainable params: 451M || all params: 905M (49.8%)` and then fails with a Metal out-of-memory error. `trainer/utils.py::freeze_model` freezes encoders by attribute name (`vision_model`, `vision_tower`, `aligner`, …), but PaddleOCR-VL's encoder is `model.visual`. Also freezing `visual` gives 12.1M trainable (1.3%), 5.7 GB peak, and training works.

Suggested fix: add `"visual"` to the names frozen in `freeze_model`, or freeze every non-language-model submodule by default.

**2) Batch size > 1.** With `--batch-size 2` (or 4), training fails in `models/paddleocr_vl/vision.py::_patch_embed`:

```
ValueError: not enough values to unpack (expected 5, got 4)
```

The batched `pixel_values` reach the patch embedding with 4 dimensions, where it expects 5. Batch size 1 with `--gradient-accumulation-steps` works as a workaround.

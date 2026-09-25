.PHONY: install test data zero-shot train-reader eval-reader teacher report
PY := uv run python -m
MODELS := paddleocr_vl chandra2 qwen35_9b
N ?= 300

install:            ## deps (incl. mlx + agent extras)
	uv sync --all-extras

test:
	uv run pytest -q

data:               ## Synthetic CNH dataset (~45 min on an M4 Pro)
	$(PY) cnh_ocr.synth.build --out data/synth --train 3000 --validation 300 --test 300
	$(PY) cnh_ocr.synth.build --out data/synth-hard --test 100 --difficulty hard --seed 7

zero-shot:          ## Stage 1 baseline: every Reader, no fine-tuning (free, local)
	for m in $(MODELS); do \
	  $(PY) cnh_ocr.reader.infer --model $$m --data data/synth/test --limit $(N) --out runs/reader/$$m-zeroshot.jsonl; \
	done

train-reader:       ## make train-reader MODEL=paddleocr_vl  (add QLORA=--qlora for the 9B)
	$(PY) cnh_ocr.reader.train_mlx --model $(MODEL) --data data/synth $(QLORA)

eval-reader:        ## make eval-reader MODEL=paddleocr_vl
	$(PY) cnh_ocr.reader.infer --model $(MODEL) --adapter runs/reader/$(MODEL)-lora \
	  --data data/synth/test --limit $(N) --out runs/reader/$(MODEL)-lora.jsonl
	$(PY) cnh_ocr.reader.infer --model $(MODEL) --adapter runs/reader/$(MODEL)-lora \
	  --data data/synth-hard/test --out runs/reader/$(MODEL)-lora-hard.jsonl

teacher:            ## Stage 2 Teacher trajectories -> LangSmith (PAID: Anthropic API)
	$(PY) cnh_ocr.extractor.run --role teacher --data data/synth/train --limit 1500 --project cnh-extractor-teacher

report:
	$(PY) cnh_ocr.evaluation.report --data data/synth/test --reader runs/reader/*.jsonl \
	  --extractor runs/extractor/*.jsonl

# keelgw-router

A four-Tier prompt classifier as an HTTP service: send it a prompt, get back
`simple`, `medium`, `complex` or `reasoning`. It's the router from
[keelgw](https://github.com/ricardocunha/keelgw), an AI gateway that uses the
Tier to pick a Model for `model: auto`.

```
POST /v1/classify  {"text": "rename x to y in utils.py"}
→ 200 {"tier": "simple", "scores": {"simple": 0.999, "medium": 0.001, ...}, "latency_ms": 8.1}
```

## Quickstart

Needs Docker, or [uv](https://docs.astral.sh/uv/) for running outside Docker.

```bash
make up                       # builds the image (downloads the ~470 MB model once), starts it
curl -s localhost:18080/v1/classify -d '{"text": "Can you change the background color of my view to blue?"}'
make down
```

Without Docker:

```bash
make setup model              # dependencies, then the pinned model into .cache/model
uv run python -m keelgw_router.server     # listens on :8080
```

## How it works

```
text → cap at 16,000 chars → tokenise ("query: " + text) → keep 256 tokens (first 96 + the end)
     → multilingual-e5-small, 12 layers, ONNX Runtime on CPU → mean-pool → L2-normalise → 384 numbers
     → head: softmax(W·x + b), W is 4 × 384 → the highest score is the Tier
```

- **The embedding model is frozen**: intfloat/multilingual-e5-small, pinned to
  a Hugging Face revision and checked by sha256 (`fetch_model.py`). It's
  downloaded, never committed.
- **The head is the only trained part**: 1,540 numbers in `model/head.json`.
  It refuses to load against a different model revision.
- **Only the latest user turn is classified.** Any other field in the request
  is ignored. In keelgw, adding three earlier turns cut accuracy from 80% to 43%.
- **One inference at a time per process.** A request waits up to
  `ROUTER_QUEUE_MS` for its turn, then gets `503 {"error": "busy"}`, so a
  caller can fall back instead of waiting.
- **Prompt text is never logged.** `/metrics` counts requests, Tiers and latency.

### The data

`dataset/prompts.jsonl` holds 4,830 synthetic coding-assistant prompts. They
were written by Qwen2.5-Coder-32B (local, through Ollama), labelled blind by
Claude Haiku 4.5, and disputes were settled by a stronger Claude model.
`dataset.py` is how they were made; it's kept for reference and calls paid
APIs, so nothing here runs it. Splits:

| train | val | eval | unsure (not used) |
|---|---|---|---|
| 2,926 | 331 | 452 | 1,121 |

**Not the same as keelgw's dataset.** keelgw's also has 646 prompts that paste
a file from its own repository with a request around it. That repository is
private, so those rows were dropped here and the head was retrained without
them. The router has therefore never trained or been measured on pasted-file
prompts in this copy.

### How good it is

From `model/metrics.json` (trained 2026-11-19), on the 452 eval prompts:

| | simple | medium | complex | reasoning | all |
|---|---|---|---|---|---|
| accuracy | 78.6% | 69.8% | 78.1% | 76.0% | **75.4%** (macro-F1 0.760) |

By prompt form: follow-ups 81.7%, bare questions 81.1%, snippets 78.6%, error
reports 68.5%, **conversation-style 53.8%**. keelgw's target was 80%; this head
is below it. The labels are synthetic, so this measures agreement with the
labelling models, not answer quality.

**What dropping the pasted rows cost.** On the same 452 eval prompts, keelgw's
head (trained with them) scores 77.0% and this one 75.4%. That's about 7
prompts, nearly all bare questions (86.8% against 81.1%). The L2 strength
chosen on val also moved, from 0.03 to 0.01.

Latency, from `metrics.json`: p50 7.3 ms and p95 19.4 ms per classification,
2 threads on an Apple M4 Pro.

## Tests

| Command | Layer | Needs | Time |
|---|---|---|---|
| `make test` | `tests/unit`: truncation, the head file, training on a fake embedder, the HTTP rules | nothing | ~7 s |
| `make test-model` | `tests/model`: model pins, a prompt per Tier, Portuguese, eval accuracy and retraining | the model (downloaded) | ~40 s first run, seconds once embeddings are cached |
| `make e2e` | `tests/e2e`: the image over HTTP, run from a container | Docker | ~2 s plus the build |
| `make test-live` | `tests/live`: **one real Anthropic API call** | a key | seconds |

`make test-all` runs everything but the live test.

**Model tests.** They check the eval accuracy against `metrics.json` and
retrain the head from the dataset with the same seed. Both must land within
one point, since ONNX results differ slightly between CPUs.

**E2E tests.** `docker compose` runs two routers from the same image:

| Service | Host port | Settings | Used for |
|---|---|---|---|
| `router` | 18080 | concurrency 1, 1,000 ms queue, 2 threads | Normal behaviour |
| `router-tight` | 18081 | concurrency 1, 50 ms queue, 1 thread | Being busy |

The scenarios cover:
- health and the pinned revision;
- a clear-cut prompt per Tier;
- four scores summing to one;
- Portuguese;
- extra fields ignored;
- a long prompt under the body limit;
- refusals: empty, blank, non-string or missing text, invalid JSON, over 64 KiB, unknown paths;
- kept-alive connections;
- 8 parallel requests all served;
- p95 latency under 800 ms;
- metrics counting;
- a burst against `router-tight` getting fast 503s and then recovering.

Against services you started yourself: `make up`, then `uv run pytest -m e2e`.

**The live test.** It makes exactly one Messages API call. It sends one
clear-cut prompt to the router and to Claude, using `dataset.py`'s own
labelling request (the same system prompt, Tier policies and JSON schema), and
checks both say `simple`.

- **It runs only through `make test-live`**, which sets `KEELGW_ROUTER_LIVE=1`.
  Nothing else sets it.
- **Without the flag it's skipped.** With the flag but no key it fails.
- **The `live` marker is also excluded from the default pytest run.**
- **The key** comes from `ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY_FILE`,
  either in the environment or in `.env` (git-ignored). It's never printed.
- **The model** is `claude-haiku-4-5`, the one that labelled the data.
  Override it with `LIVE_LABEL_MODEL`.

### Measured in this repo (2026-11-19, Apple M4 Pro, Docker Desktop)

- **`make test`:** 52 passed.
- **`make test-model`:** 7 passed.
  - Eval accuracy reproduced: 0.754.
  - Retraining from the dataset gave the same L2 and accuracy.
- **`make e2e`:** 21 passed.
  - Inference p50 16.5 ms inside the container; wall-clock p95 73 ms over 25 requests.
  - The burst of 16 against `router-tight`: 2 served, 14 got a 503.
  - The 503s took 0.06–1.08 s, not ~50 ms. A likely cause is the HTTP server's
    listen backlog (`ThreadingHTTPServer` defaults to 5): extra simultaneous
    connections are dropped and the client's TCP retries after about a second.
    That's not verified. All of them still came back under the 1.5 s at which
    keelgw's gateway gives up.
- **`make test-live`:** not run here; it spends money on your key.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | 8080 | Listen port |
| `ROUTER_THREADS` | 2 | ONNX Runtime threads per inference |
| `ROUTER_CONCURRENCY` | 1 | Inferences at once |
| `ROUTER_QUEUE_MS` | 1000 | Wait for a slot before a 503 |
| `ROUTER_METRICS_PORT` | 0 | Also serve `/metrics` on this port |
| `ROUTER_MODEL_DIR` | `.cache/model` | The pinned model files |
| `ROUTER_HEAD` | `model/head.json` | The head |
| `ROUTER_HOST_PORT`, `ROUTER_TIGHT_HOST_PORT` | 18080, 18081 | Compose host ports |

## Retraining

`make train` re-embeds the dataset (cached in `.cache/embeddings`), picks the
L2 strength on val by macro-F1, and rewrites `model/head.json` and
`model/metrics.json`. It makes no API calls. Changing the truncation in
`classifier.py` changes the embedding cache keys, so the head has to be
retrained after it.

## Origin and licence

Copied from keelgw's `router/` at commit c94a975 (2026-10-15). The package
was renamed and the paths adapted. The dataset's pasted-file prompts were
dropped, and the head and metrics were retrained here on 2026-11-19. Licensed
[MIT](../LICENSE).
- **Embedding model:** MIT per its model card; downloaded at build time, not
  redistributed.
- **Labels:** the dataset's labels came from Claude models. Check Anthropic's
  terms before using them to train something else.

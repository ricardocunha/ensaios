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

## Architecture

![keelgw-router: from prompt to Tier](../images/router.en.svg)

*The source and an interactive version are in [`../images`](../images/).*

A request goes through five steps, all in one Python process:

1. **Admit.** One inference runs at a time. A request that can't get the slot
   within `ROUTER_QUEUE_MS` (1,000 ms) gets `503 {"error": "busy"}`, and the
   caller uses a fallback Tier instead of waiting.
2. **Prepare.** The text is capped at 16,000 characters, prefixed with
   `query: ` and tokenised. Then it's cut to 256 tokens: the first 96 plus as
   much of the end as fits.
3. **Embed.** multilingual-e5-small runs on ONNX Runtime on CPU. It's
   **frozen**: pinned to a Hugging Face revision, checked by sha256
   (`fetch_model.py`), and downloaded rather than committed. Its 12 layers
   give one vector per token, which are mean-pooled and L2-normalised into 384
   numbers.
4. **Decide.** The head is a logistic regression, `softmax(W·x + b)` with `W`
   4 × 384. It's 1,540 numbers in `model/head.json`, **the only trained part**,
   and it refuses to load against a different model revision. The highest
   score is the Tier.
5. **Answer.** The response carries `{tier, scores, latency_ms}`. Prompt text
   is never logged; `/metrics` counts requests, Tiers and latency.

**Offline,** `train.py` fits the head from `dataset/prompts.jsonl` in seconds,
with no API calls (see [Retraining](#retraining)).

**Docker Compose** runs the same image twice, a normal `router` and a
`router-tight` built to be busy, plus an `e2e` container that tests both over
HTTP (see [Tests](#tests)).

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

## Trade-offs

| Choice | What it gains | What it gives up |
|---|---|---|
| A frozen e5 on CPU | No GPU, no torch, milliseconds, prompts stay local, MIT licence | e5 learned meaning, not difficulty: a rename and a redesign on the same topic look alike, which is where `medium` gets confused |
| A multilingual model | About 100 languages, Portuguese included | Size: the 250k-piece vocabulary is most of the ~470 MB model |
| 256 tokens, first 96 + the end | Bounded latency, so a 60 KB paste costs the same as a short prompt; the ask is caught above or below a paste. In keelgw, 512 tokens doubled the time for no accuracy | The middle of a long prompt is never read |
| Only the latest user turn | A short new ask isn't drowned by earlier turns (in keelgw, three earlier turns cut accuracy from 80% to 43%) | No conversation context: "now do the same for the other twelve services" looks simple |
| A linear head, argmax, no threshold | Retrains in seconds on a few thousand labels; can be inspected; always answers | Straight boundaries cap accuracy; a 0.30 / 0.29 near-tie is decided as firmly as 0.95 |
| One inference at a time, short queue, 503 | Predictable latency; a busy router says so at once, so the caller falls back | Throughput comes only from more processes |
| Synthetic labels from two model families | Thousands of labels for a few dollars, with no real user data | It measures agreement with the labelling models, not answer quality |
| The Python standard library HTTP server | No web framework to depend on | A listen backlog of 5: bursts can make some connections retry after about a second (see [Performance](#performance)) |

## Performance

### Accuracy

From `model/metrics.json` (trained 2026-11-19), on the 452 eval prompts:

| | simple | medium | complex | reasoning | all |
|---|---|---|---|---|---|
| accuracy | 78.6% | 69.8% | 78.1% | 76.0% | **75.4%** (macro-F1 0.760) |

- **By prompt form:** follow-ups 81.7%, bare questions 81.1%, snippets 78.6%,
  error reports 68.5%, **conversation-style 53.8%**.
- **Against the target:** keelgw's target was 80%, and this head is below it.
- **What it measures:** the labels are synthetic, so this is agreement with the
  labelling models, not answer quality.
- **What dropping the pasted rows cost:** on the same 452 eval prompts, keelgw's
  head (trained with them) scores 77.0% and this one 75.4%. That's about 7
  prompts, nearly all bare questions (86.8% against 81.1%). The L2 strength
  chosen on val also moved, from 0.03 to 0.01.

### Latency and load

| Where | What | Result |
|---|---|---|
| In process, `metrics.json` | One classification at a time, 2 threads, Apple M4 Pro, 210 prompts | p50 **7.3 ms**, p95 **19.4 ms**, max 21.7 ms |
| In Docker, `make e2e` | Inference time reported by the router | p50 16.5 ms |
| In Docker, `make e2e` | Wall-clock over HTTP, 25 requests (5 fill all 256 tokens) | p50 17.3 ms, p95 72.7 ms |
| In Docker, `make e2e` | 8 parallel requests on `router` | All 8 served |
| In Docker, `make e2e` | 16 at once on `router-tight` (1 slot, 50 ms queue, 1 thread) | 2 served, 14 got 503 in 0.06–1.08 s |

- **Most of the time is the transformer.** The head takes microseconds, and a
  prompt that fills all 256 tokens is the slowest case.
- **Throughput.** Each process does roughly 1 ÷ latency classifications a
  second; to serve more, run more processes.
- **The slow 503s.** Some took about a second instead of about 50 ms. The likely
  cause is the HTTP server's listen backlog of 5: extra simultaneous
  connections are dropped and the client's TCP retries after about a second.
  That isn't verified. Every 503 still came back under the 1.5 s at which
  keelgw's gateway gives up.

## Tests

| Command | Layer | Needs | Time |
|---|---|---|---|
| `make test` | `tests/unit`: truncation, the head file, training on a fake embedder, the HTTP rules | nothing | ~7 s |
| `make test-model` | `tests/model`: model pins, a prompt per Tier, Portuguese, eval accuracy and retraining | the model (downloaded) | ~40 s first run, seconds once embeddings are cached |
| `make e2e` | `tests/e2e`: the image over HTTP, run from a container | Docker | ~2 s plus the build |
| `make test-live` | `tests/live`: **two real Anthropic API calls**, a simple and a complex prompt | a key | seconds |

`make test-all` runs everything but the live test.

### Running the tests

**What you need:**
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 and the locked dependencies.
- Docker with Compose v2, for `make e2e` and `make test-live` only.
- About 1 GB of disk for the model and the images.

Run every command from `code/`.

**1. Install the dependencies (once):**

```bash
cd code
make setup        # uv sync --frozen
```

**2. Unit tests.** No model, no network, no Docker:

```bash
make test
```

**3. Model tests.** The first run downloads the pinned model (~470 MB,
sha256-checked) into `.cache/model` and embeds the eval set into
`.cache/embeddings`. Later runs reuse both:

```bash
make test-model
```

**4. End-to-end tests.** Builds the image, starts `router` and `router-tight`,
runs `tests/e2e` from the `e2e` container, and tears everything down even if a
test fails:

```bash
make e2e
```

The first build downloads the model into the image, so it takes a few minutes.
Ports 18080 and 18081 must be free. If they aren't, set `ROUTER_HOST_PORT` and
`ROUTER_TIGHT_HOST_PORT` in `.env`.

**5. Everything except the live test,** lint included:

```bash
make test-all
```

**6. The live tests (optional, a fraction of a cent).** Put a key in
`.env`, then run the one target that enables it:

```bash
cp .env.example .env    # then set ANTHROPIC_API_KEY or ANTHROPIC_API_KEY_FILE
make test-live
```

**Running part of a suite.** Pass pytest's usual options through `uv run`.
Because `pyproject.toml` deselects `model`, `e2e` and `live` by default, name
the marker for those suites:

```bash
uv run pytest tests/unit/test_router.py -k busy     # one unit file, matching tests
uv run pytest -m model tests/model -k portuguese    # one model test
make up && uv run pytest -m e2e; make down          # e2e from the host, against your own services
```

From the host, the e2e tests use `ROUTER_URL` and `ROUTER_TIGHT_URL`
(defaults `http://localhost:18080` and `http://localhost:18081`).

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

**The live tests.** Two of them, one Messages API call each: a clear-cut
`simple` prompt and a clear-cut `complex` one (`tests/prompts.json`, `live`).
Each sends the prompt to the router and to Claude, and checks both give the
expected Tier.

Claude is there because the head learned its Tiers from Claude's labels, so it's
the reference the router imitates. The call uses `dataset.py`'s own labelling
request: the same system prompt, Tier policies and JSON schema.

- **It runs only through `make test-live`**, which sets `KEELGW_ROUTER_LIVE=1`.
  Nothing else sets it.
- **Without the flag it's skipped.** With the flag but no key it fails.
- **The `live` marker is also excluded from the default pytest run.**
- **The key** comes from `ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY_FILE`,
  either in the environment or in `.env` (git-ignored). It's never printed.
- **The model** is `claude-haiku-4-5`, the one that labelled the data.
  Override it with `LIVE_LABEL_MODEL`.
- **It prints a walkthrough** of the diagram's steps. The same flag starts the
  router with `ROUTER_TRACE=1`, so the test can show the slot wait, the
  characters and token pieces, any truncation, the embedding, the head's logits
  and scores, then the cross-check: Claude's label, tokens and cost. Other runs never turn the
  trace on, and an e2e test checks that a router without it ignores
  `"trace": true`.

### Measured in this repo (2026-11-19, Apple M4 Pro, Docker Desktop)

| Command | Result |
|---|---|
| `make test` | 54 passed |
| `make test-model` | 9 passed; eval accuracy 0.754 reproduced, and retraining from the dataset gave the same L2 and accuracy |
| `make e2e` | 22 passed; latency and load figures are under [Performance](#performance) |
| `make test-live` | 2 passed: Claude Haiku 4.5, the router and the expected Tier agreed on `simple` and on `complex`; about $0.0015 for both calls |

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
| `ROUTER_TRACE` | 0 | 1 lets a request ask for `"trace": true` and get each step's counts and timings back. Compose sets it only during `make test-live` |
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

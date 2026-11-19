# keelgw-router

keelgw's four-Tier prompt router on its own: an HTTP service that classifies a
prompt as simple, medium, complex or reasoning. Everything runnable is in
`code/`, an independent uv project. Run commands from `code/`; `make help`
lists them.

## Layout

```
images/                  the architecture diagram: archify source, HTML, SVG and PNG exports
code/
├── src/keelgw_router/
│   ├── classifier.py    Embedder (e5 on ONNX), prepare() truncation, Head
│   ├── server.py        HTTP: POST /v1/classify, GET /healthz, GET /metrics
│   ├── fetch_model.py   pinned model download, sha256-checked (stdlib only)
│   ├── train.py         fits model/head.json from dataset/prompts.jsonl
│   └── dataset.py       how the data was made (reference; calls Ollama and the API)
├── model/               head.json and metrics.json: the shipped head
├── dataset/prompts.jsonl   the labelled data (the only dataset file in git)
├── tests/
│   ├── prompts.json     the prompts the tests assert on
│   ├── unit/            no model, no network
│   ├── model/           real model in process (marker: model)
│   ├── e2e/             HTTP against the compose services (marker: e2e)
│   └── live/            TWO real Anthropic API calls (marker: live)
├── Dockerfile           targets: runtime (default) and e2e
└── docker-compose.yml   router :18080, router-tight :18081, e2e (profile)
```

## Commands

| Command | What it does |
|---|---|
| `make test` | Unit tests, seconds. The default pytest run. |
| `make test-model` | Downloads the model if needed, then the model tests (~40 s). |
| `make e2e` | Builds the image, starts both routers, runs tests/e2e in a container, tears down. |
| `make up` / `make down` | Start or stop the routers for manual calls. |
| `make train` | Retrains the head from the dataset (no API calls); overwrites model/. |
| `make test-live` | The two real API calls. Only when asked. |
| `make lint` / `make fmt` | ruff. |

## Rules

- **No real API calls in tests**, except `tests/live`, which runs only through
  `make test-live` (it sets `KEELGW_ROUTER_LIVE=1`). Never set that variable in
  another target, in `.env.example` or in CI. Never run `make test-live`
  unless the user asks: it spends money on their key.
- **Never print, log or commit a key.** `.env` is git-ignored.
- **Never commit the model** (`.cache/`, ~470 MB) or cached embeddings. The
  image and `make model` download it at the revision pinned in `fetch_model.py`.
- **The head and the model revision go together.** `Head.load` refuses a head
  trained on another revision. Changing the pin in `fetch_model.py` means
  retraining (`make train`) and updating `tests/prompts.json` if a prompt's
  margin drops.
- **Training and serving share `classifier.py`.** Change the truncation in
  `prepare()` or `Embedder.ids()` and the embedding cache keys change, so the
  head must be retrained; `train.py` keys the cache on that code.
- **Only the latest user turn is classified.** The server ignores any other
  field; adding earlier turns cut accuracy from 80% to 43% in keelgw.
- **Never echo prompt text** in logs or errors; the server logs only counts.
- **`model/metrics.json` is the source of the numbers.** The model tests check
  the head against it within one point; don't edit it by hand.
- **Tests assert only on prompts with a wide margin** (top score 0.96+, from
  the eval split). Add new asserted prompts to `tests/prompts.json` after
  checking their scores with the real model.
- Python 3.12, uv, ruff (line length 130). Dependencies change through
  `pyproject.toml` and `uv lock`.

## Where it came from

Copied from keelgw's `router/` at commit c94a975 (2026-10-15). The dataset's
646 pasted-file prompts were dropped, because they quote keelgw's private
source, and the head was retrained here on the rest (2026-11-19). keelgw
itself is private; this copy is MIT licensed. Never add prompts that quote a
private repository: this repository is public.

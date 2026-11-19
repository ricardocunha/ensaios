# keelgw-router: a four-Tier prompt router you can run

**Status:** code only, no article yet · **Branch:** `article/2026-11-keelgw-router`

The prompt router from [keelgw](not public yet), an AI
gateway, taken out on its own so it can be run and tested end to end. For
`model: auto`, the gateway asks it which of four Tiers a prompt needs (simple,
medium, complex, reasoning) and maps the Tier to a Model.

It's a frozen multilingual embedding model (intfloat/multilingual-e5-small, on
ONNX Runtime, CPU only) plus a logistic-regression head trained on synthetic,
LLM-labelled prompts: 1,540 trained numbers. The shipped head scores **75.4%**
on 452 held-out synthetic prompts (`code/model/metrics.json`, trained
2026-11-19), below keelgw's 80% target.

![keelgw-router: from prompt to Tier](images/router.en.svg)

## Run the tests

From `code/`, with [uv](https://docs.astral.sh/uv/) and Docker:

```bash
make setup        # dependencies, once
make test         # unit: no model, no network, seconds
make test-model   # the real model in process (downloads ~470 MB the first time)
make e2e          # the Docker image over HTTP, from a container
make test-live    # optional: ONE real Anthropic API call, needs a key in .env
```

Step-by-step details are in [code/README.md](code/README.md#running-the-tests).

| | |
|---|---|
| Code, how to run and test it | [code/README.md](code/README.md) |
| Working on it with Claude Code | [CLAUDE.md](CLAUDE.md) |
| Diagram source | [images/](images/) |
| Licence | [MIT](LICENSE) |

## Published

- LinkedIn: [[LINK]]

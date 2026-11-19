# keelgw-router: a four-Tier prompt router you can run

**Status:** code only, no article yet · **Branch:** `article/2026-11-keelgw-router`

The prompt router from [keelgw](https://github.com/ricardocunha/keelgw), an AI
gateway, taken out on its own so it can be run and tested end to end. For
`model: auto`, the gateway asks it which of four Tiers a prompt needs (simple,
medium, complex, reasoning) and maps the Tier to a Model.

It's a frozen multilingual embedding model (intfloat/multilingual-e5-small, on
ONNX Runtime, CPU only) plus a logistic-regression head trained on synthetic,
LLM-labelled prompts: 1,540 trained numbers. The shipped head scores **75.4%**
on 452 held-out synthetic prompts (`code/model/metrics.json`, trained
2026-11-19), below keelgw's 80% target.

![keelgw-router: from prompt to Tier](images/router.en.svg)

| | |
|---|---|
| Code, how to run and test it | [code/README.md](code/README.md) |
| Working on it with Claude Code | [CLAUDE.md](CLAUDE.md) |
| Diagram source | [images/](images/) |
| Licence | [MIT](LICENSE) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]

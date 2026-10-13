# ensaios

*Essays you can run.* In Portuguese, **ensaio** means both an *essay* and a *trial*: each article here is both, a technical field report plus the working code behind it. Every article is written in English and published on Medium, LinkedIn, dev.to / Hashnode and other platforms. Each one lives in its own folder, with its drafts and a runnable project side by side.

## Articles

| Article | Status | Folder |
|---|---|---|
| [My eye-scan RAG cited its sources. It was reading the labels.](articles/2027-01-multimodal-medical-rag-eye/) | published 2026-10-13 | `articles/2027-01-multimodal-medical-rag-eye/` |

<!-- Add one row per article when it's merged into main:
| [Title](articles/yyyy-mm-slug/) | published YYYY-MM-DD · [Medium](…) · [LinkedIn](…) | `articles/yyyy-mm-slug/` |
-->

## Layout

```
articles/<yyyy-mm>-<slug>/
├── README.md          # what the article is about, status, links
├── article-en.md      # long-form draft
├── linkedin-en.md     # LinkedIn post
└── code/              # the article's own project (own dependencies, tests, Makefile)
_template/             # copy this to start a new article
scripts/               # repo-wide helpers (e.g. check-article.sh)
```

Each `code/` folder is an independent project, so articles never share or break each other's dependencies.

## Workflow

Each article is written on its own branch, `article/<yyyy-mm>-<slug>`, and merged into `main` when it's published. See [CONTRIBUTING.md](CONTRIBUTING.md).

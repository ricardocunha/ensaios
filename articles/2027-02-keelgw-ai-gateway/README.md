# A prompt router for $1.88: what synthetic labels buy, and what they don't

**Status:** drafts complete (EN, EN Medium, PT-BR, LinkedIn EN/PT-BR); numbers final and mapped in SOURCES.md; proofread; before publishing: check provider terms for training on Claude's labels, read the Arch-Router licence, re-verify third-party claims; links pending publication · **Branch:** `article/2027-02-keelgw-ai-gateway` · **Target date:** 2027-02-05

> **Built and verified locally only.** The keelgw gateway has never run in a real AWS account, sent a request to a real model provider or served a customer. Every measurement was taken on a laptop; the only calls to a real API were the labelling batches for the training data.

A field report on [keelgw](https://github.com/ricardocunha/keelgw) (Keel Gateway), a multi-tenant AI gateway for small businesses, told through its prompt router. For `model: auto` the gateway classifies a prompt into four Tiers (simple, medium, complex, reasoning). The open router model first planned turned out, by the project's notes on its licence, not to be usable in a hosted product, so he trained a small CPU classifier (multilingual-e5-small on ONNX plus a logistic-regression head) in about 26 hours from synthetic data: 4,412 prompts written locally by Qwen2.5-Coder-32B, relabelled blind by Claude Haiku 4.5, with 2,006 disputes adjudicated by Claude Opus 5.5, for $1.88 of API spend. The first two models agreed on 54.5 % of the prompts (84.2 % on simple, 33.8 % on reasoning). The classifier scores 80.0 % accuracy (macro-F1 0.8034) on 400 held-out synthetic prompts, with p50 7.3 ms and p95 20.9 ms on an Apple M4 Pro. The article states what that leaves out: one training choice was made on the eval set (79.3 % vs 80.0 %, about three prompts; 95 % Wilson interval 75.8 % to 83.6 %), 63 of the 80 errors are a neighbouring Tier and 17 are not, the review file has no recorded labels, the gateway has never called the trained router, and nothing measures Spend saved or answer quality. It then widens to the gateway's design (a Go streaming proxy that never translates protocols, a 13-step pipeline, integer micro-dollar Spend, reserve-then-settle Quota, 403 instead of 429) and its local load tests, where a 29.4 s p99 measured the AWS emulator's queue. See [SOURCES.md](SOURCES.md) for the source of every number.

| | |
|---|---|
| Article (EN) | [article-en.md](article-en.md) · Medium version: [article-en-medium.md](article-en-medium.md) |
| Article (PT-BR) | [article-pt-br.md](article-pt-br.md) |
| LinkedIn | [EN](linkedin-en.md) · [PT-BR](linkedin-pt-br.md) |
| Project repo | [github.com/ricardocunha/keelgw](https://github.com/ricardocunha/keelgw) |
| Sources | [SOURCES.md](SOURCES.md) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]

---
title: "A prompt router for $1.88: what synthetic labels buy, and what they don't"
subtitle: "I needed a four-Tier prompt classifier for an AI gateway, the open model I had planned on turned out not to be usable, and I trained my own on CPU in about a day from synthetic data. It hit its 80 % target. Here is everything that number leaves out."
platforms: Medium (short version; the full version is article-en.md, for dev.to / Hashnode)
status: DRAFT — numbers final (each one is mapped to the keelgw repo in SOURCES.md); third-party claims to re-verify before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-02-keelgw-ai-gateway
---

# A prompt router for $1.88: what synthetic labels buy, and what they don't

> **Built and verified locally only.** As of the last commit described here (2026-10-06), keelgw has never run in a real AWS account, called a real model provider or served a customer. Every number below comes from a laptop.

I've been building [keelgw](https://github.com/ricardocunha/keelgw) (Keel Gateway), a multi-tenant AI gateway for small businesses: which Models each Member may reach, through which Clients (Claude Code, Claude Cowork, Codex), at what USD Spend, on the Organization's own provider accounts.

One feature is `model: auto`: the gateway classifies the prompt into one of four Tiers (**simple, medium, complex, reasoning**), and a Tier Map says which allowed Model serves each Tier. That needs a prompt router. I had picked an open router model, then read its licence properly. So I trained my own small CPU classifier from synthetic data, in about 26 hours from the first data-generation commit to the committed model.

The short version: the data cost **$1.88** in API spend. The classifier scores **80.0 %** on 400 held-out prompts, exactly its target, after one training decision I made while looking at that set. The gateway has never called it, and nothing measures whether it saves Spend or keeps answers good.

## The plan that didn't survive a licence check

The design first named Arch-Router-1.5B, "on the belief that it was Apache-2.0", as the design doc now puts it. On 2026-09-30 I recorded a blocker: as I read the model's licence that day, it is the Katanemo licence, which requires a separate commercial licence from DigitalOcean for any commercial use, including offering the model as a service. The fallback, RouteLLM, didn't fit either, by my notes: two classes where I needed four, recommended routers that call OpenAI's embeddings API for every prompt, and self-hosted checkpoints with no licence. These are my notes from October 2026 about other people's projects; check them before relying on them.

So: my own classifier, on CPU, sending nothing outside the gateway.

## The classifier and the data

- **Model:** `intfloat/multilingual-e5-small` (MIT per its model card) as an ONNX export on CPU, plus a 4-way logistic regression in a JSON file of about 21 KB. Input: the latest user turn plus earlier turns, at most 8,000 characters.
- **Generation:** Qwen2.5-Coder-32B on Ollama, locally, wrote 4,412 distinct prompts over a grid of Tier × 12 stacks × 4 prompt shapes, some in Portuguese, Spanish, German and French.
- **Relabel:** Claude Haiku 4.5 labelled every prompt again, without being told which Tier it was written for.
- **Adjudication:** Claude Opus 5.5 decided the 2,006 prompts where the two disagreed or the relabeller wasn't confident.
- **Cost:** $1.88 for the relabel and the adjudication together. Generation was local.
- **Splits:** eval 400 (100 per Tier), validation 303, train 2,706. The 1,003 prompts Opus wasn't sure of were set aside.

## Where the models disagreed

| Written for | Prompts | Agreed, relabel confident |
|---|---|---|
| simple | 745 | 627 (84.2 %) |
| medium | 742 | 534 (72.0 %) |
| complex | 1,451 | 747 (51.5 %) |
| reasoning | 1,474 | 498 (33.8 %) |
| **all** | **4,412** | **2,406 (54.5 %)** |

**The local model couldn't write hard prompts on demand.** Of the 1,474 prompts it wrote as reasoning, the relabeller called 549 reasoning and 537 medium. One example: *"Getting `OperationalError: (1215, 'Cannot add foreign key constraint')` when running a migration. Any ideas?"* Haiku and Opus both called it medium. A second generation round with a stricter hint raised agreement on reasoning from 28.9 % to 38.7 %. Better, not fixed.

**Opus was confident on exactly half of the disputes**: 1,003 of 2,006. Some of the unsure ones are a pasted stack trace with no question at all. The Tier definitions describe the work an answer needs, and a stack trace alone doesn't state the ask.

## A decision I reversed the same day

What about the 1,003 unsure verdicts? At 10:42 on 2026-10-06 I committed "they train but never measure". Three and a half hours later I committed the opposite:

| Training set | Val accuracy | Eval accuracy |
|---|---|---|
| confident labels + 1,003 unsure | 79.2 % | 79.3 % |
| **confident labels only (2,706)** | **82.2 %** | **80.0 %** |

More labels made it worse. But I chose between the two rows after seeing both columns, and the second column is the eval set. The moment I used it to choose, it stopped being held out.

## Results

Eval, 400 prompts: **accuracy 80.0 %, macro-F1 0.8034**. The target was at least 80 %.

| True ↓ / predicted → | simple | medium | complex | reasoning |
|---|---|---|---|---|
| simple | **82** | 16 | 2 | 0 |
| medium | 7 | **77** | 10 | 6 |
| complex | 2 | 20 | **76** | 2 |
| reasoning | 1 | 6 | 8 | **85** |

- **Medium is the sink.** Predicted 119 times, right 77 times (precision 0.647).
- **My notes say "almost every error is a neighbouring Tier". The matrix says 63 of 80.** The other 17 are two or three Tiers away.
- **Latency** on an Apple M4 Pro, 2 threads, one request at a time: p50 7.3 ms, p95 20.9 ms over 210 requests, mostly short prompts. The target is a p95 of at most 800 ms on a c7i.xlarge. I have never measured it there.

## What the 80 % doesn't tell you

1. **It was selected on the eval set.** With 320 of 400 correct, the 95 % Wilson interval is 75.8 % to 83.6 %. The 0.7-point gap between the two training choices is about three prompts.
2. **Train and eval come from the same generator and grid.** Exact duplicates are removed; nothing checks for near-duplicates.
3. **The labels are models' labels.** The pipeline writes a 150-row sample for me to review. The review file in the repo has no recorded corrections or labels.
4. **Eval leaves out the hard cases by construction.** The unsure prompts are 22.7 % of the data.
5. **The gateway has never called this classifier.** Locally its configuration points at a mock router.
6. **Nothing measures what the router is for.** No Spend comparison, no check of answer quality. I can't claim it saves money or preserves quality.

What the synthetic labels did buy: a reproducible pipeline, a classifier whose errors I can read in a table, a measurement of where my own Tier definitions are ambiguous, and a baseline to beat when real, consented traffic exists.

## The rest of the gateway, and its load tests

The data plane is a first-party Go streaming proxy that never translates between protocols, so request bodies pass byte for byte apart from the `model` field. One pipeline of 13 fixed steps. Spend is integer micro-dollars, with reserve-then-settle Quota in Valkey. An exhausted Quota returns 403, not 429, because coding clients retry 429s. Everything runs on a laptop: kind, floci emulating AWS, and a mock provider.

The worst local load-test number, a **29.4 s p99** at 500 concurrent streams, measured the emulator: its SQS took 1.1 s to accept a batch of 10 (longer on the encrypted queue), roughly 30 records a second, so the gateway's buffer filled and it waited rather than drop a Request Log record, as designed. At 20 streams the median overhead was about 0.6 ms. The tests still found real bugs: one queue sender became 16, the buffer now drains on shutdown, and an MCP path that was OOMKilled at 100 calls a second got its uploads moved off the request path (then +0.7 ms at p95). `auto` added about 6 ms at p95 against a mock router.

None of this says the gateway is fast in production. There is no staging run. The repo has 178 commits over 9 active days, most co-authored with a coding agent, and its runbook says: "The AWS account doesn't exist yet and nothing has been applied."

## What I'd tell a team

1. **Read the licence before you design around a model.**
2. **Use label disagreement as a measurement.** 84.2 % agreement on simple and 33.8 % on reasoning showed where my Tier definitions are vague before any classifier existed.
3. **Don't trust a generator to hit a hard class.** A stricter second round helped by about 10 points. It didn't fix it.
4. **More labels can be worse labels.** Try it both ways, and decide on validation only.
5. **Write down the moment you looked at the eval set.** The number is still useful. It isn't what "held-out" promises.
6. **Ask what your slowest local number is measuring**, and keep "built" apart from "verified where it will run".

---

**Project:** [github.com/ricardocunha/keelgw](https://github.com/ricardocunha/keelgw) · **Drafts and the source of every number:** [github.com/ricardocunha/ensaios › articles/2027-02-keelgw-ai-gateway](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-02-keelgw-ai-gateway)

*Models: intfloat/multilingual-e5-small (MIT per its model card); Qwen2.5-Coder-32B (Apache-2.0) on Ollama; Claude Haiku 4.5 and Claude Opus 5.5 for labels. Statements about Arch-Router and RouteLLM are my notes as recorded in the project's design documents in September and October 2026.*

#AI #LLM #MachineLearning #Evaluation #SyntheticData #OpenSource #AIGateway

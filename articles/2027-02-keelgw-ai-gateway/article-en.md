---
title: "A prompt router for $1.88: what synthetic labels buy, and what they don't"
subtitle: "I needed a four-Tier prompt classifier for an AI gateway, the open model I had planned on turned out, as I read its licence, not to be usable in a hosted product, and I trained my own on CPU in about a day from synthetic data. It hit its 80 % target. Here is everything that number leaves out."
platforms: Medium, dev.to, Hashnode
status: DRAFT — numbers final (each one is mapped to the keelgw repo in SOURCES.md); third-party claims to re-verify before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2027-02-keelgw-ai-gateway
---

# A prompt router for $1.88: what synthetic labels buy, and what they don't

> **Built and verified locally only.** As of the last commit described here (2026-10-06), the keelgw gateway has never run in a real AWS account, sent a request to a real model provider or served a customer. Every measurement below was taken on a laptop. The only calls to a real API were the labelling batches for the training data.

I've been building [keelgw](https://github.com/ricardocunha/keelgw) (Keel Gateway), a multi-tenant AI gateway for small businesses. It governs which Models each Member of an Organization may reach, through which Clients (Claude Code, Claude Cowork, Codex), and at what USD Spend, always on the Organization's own provider accounts.

One feature is `model: auto`: the gateway classifies the prompt into one of four Tiers (simple, medium, complex, reasoning), and a Tier Map says which allowed Model serves each Tier. That needs a prompt router. I had picked an open router model, then read its licence properly. So I trained my own small classifier, on CPU, from synthetic data, in about 26 hours from the first commit of the data-generation script to the committed model.

The short version:

- **The data cost $1.88 in API spend.** A local open model wrote 4,412 prompts, Claude Haiku 4.5 relabelled all of them blind, and Claude Opus 5.5 adjudicated the 2,006 disputes.
- **The first two models agreed on 54.5 % of the prompts** (same Tier, with the relabeller confident). Agreement fell as the Tier rose: 84.2 % for prompts written as simple, 33.8 % for prompts written as reasoning.
- **The classifier scores 80.0 % on 400 held-out synthetic prompts**, exactly the target. I made one training decision while looking at that set, so it isn't a clean held-out number.
- **None of this says it works on real traffic.** The gateway has never called the trained router, and nothing measures Spend saved or answer quality.
- **The rest of the gateway has the same status**: built, tested locally, and the worst load-test number I recorded (a 29.4 s p99) measured the AWS emulator, not the gateway.

Every number is mapped to a file, line or commit of the keelgw repo in [SOURCES.md](https://github.com/ricardocunha/ensaios/blob/main/articles/2027-02-keelgw-ai-gateway/SOURCES.md).

## Why the gateway needs a router

A Profile in keelgw lists the Models a Member may use. For `auto`, the classifier returns only a Tier, never a Model name, and the Profile's Tier Map turns the Tier into one of the allowed Models. So swapping the classifier never changes what a Member can reach.

Each Tier is defined in one sentence, shared by the gateway and the training script. *Simple* is short, mechanical requests: renames, formatting, lookups. *Medium* is ordinary coding tasks: implementing a function, fixing a clear bug. *Complex* is large or multi-step work: multi-file changes, debugging with unclear causes. *Reasoning* is hard problems: architecture decisions, algorithms, proofs, subtle concurrency or security analysis.

If the built-in Router doesn't answer within 1,500 ms, the request uses the Profile's fallback Tier. Classification never refuses a request.

## The plan that didn't survive a licence check

The design first named Arch-Router-1.5B, a small generative model that matches a prompt against policies written in natural language, "on the belief that it was Apache-2.0", as the design doc now puts it. On 2026-09-30 I recorded a blocker: as I read the model's licence that day, it is the Katanemo licence, which requires a separate commercial licence from DigitalOcean for any commercial use, including offering the model as a service. A hosted gateway that serves the model would be exactly that.

The fallback candidate was RouteLLM. The design doc records why it didn't fit either: it routes between two classes (strong and weak) and I needed four; its recommended routers call OpenAI's embeddings API for every prompt; and its self-hosted checkpoints carry no licence, although its code is Apache-2.0. These are my notes about other people's projects, written in September and October 2026. Check them before relying on them.

On 2026-10-03 I decided to train my own: four Tiers natively, no GPU, nothing sent outside the gateway, every part under a licence I can ship.

## The classifier: an embedding model and a 21 KB head

```
latest user turn (+ earlier turns, at most 8,000 characters in all)
        │
        ▼
intfloat/multilingual-e5-small, ONNX Runtime on CPU ─► 384-dimension embedding
        │
        ▼
logistic regression, 4 outputs: softmax(Wx + b) ─► Tier + scores
```

The embedding model is `intfloat/multilingual-e5-small` (MIT, per its model card's licence metadata), pinned to a Hugging Face revision and checked by sha256 at build time. I chose a multilingual model because Members will write in other languages too. It runs as an ONNX export, with no torch in the image. The head is a multinomial logistic regression with class-balanced weights, in a JSON file of about 21 KB. Its L2 strength is picked on the validation split by macro-F1.

The model reads 512 tokens: the latest user turn first, then earlier turns in whatever room is left. The service never logs prompt text. The image is about 0.76 GB, of which the model is 487 MB.

## The data: 4,412 prompts and three models

I had no real traffic to label, so the data is synthetic.

```
grid: Tier × 12 stacks × 4 prompt shapes, 16 prompts per cell
      round 1: 4 Tiers (192 cells) · round 2: complex and reasoning again (96 cells)
        │  Qwen2.5-Coder-32B on Ollama, on the laptop
        ▼
4,412 distinct prompts, each written for a Tier
        │  Claude Haiku 4.5, Batches API, not told that Tier
        ▼
same Tier, relabel confident: 2,406 ───────────────────────┐
disputed: 2,006 ─► Claude Opus 5.5 ─┬► confident: 1,003 ───┴► 3,409 labelled prompts
                                    └► unsure: 1,003, set aside
        ▼
eval 400 (100 per Tier) · val 303 · train 2,706
```

**Generation.** Qwen2.5-Coder-32B, running locally on Ollama, wrote prompts "a developer types into a coding assistant" for each Tier, over 12 stacks (Python and Django, Go services, SQL and PostgreSQL, Terraform and Kubernetes YAML and so on) and 4 shapes: a bare request, a pasted snippet, a pasted error, a follow-up turn. A third of the cells asked for 4 of their 16 prompts in Portuguese, Spanish, German or French. Each request also asked for at least three prompts that would fool a length-based guess: long prompts with an easy ask, short prompts with a hard one.

**Relabel.** Claude Haiku 4.5 labelled every prompt again without knowing which Tier it was written for, 20 shuffled prompts per request, and said whether it was confident.

**Adjudication.** A prompt counts as agreed when the relabel matches the Tier it was written for and the relabeller was confident. The other 2,006 went to Claude Opus 5.5, which saw both suggestions and was told either may be wrong.

**Cost.** Generation was local and free. The relabel and the adjudication together cost $1.88. The script refuses to start a paid phase whose estimate would take the total past its budget, 3 dollars by default.

## Where the models disagreed

| Written for | Prompts | Agreed, relabel confident | Sent to adjudication |
|---|---|---|---|
| simple | 745 | 627 (84.2 %) | 118 (15.8 %) |
| medium | 742 | 534 (72.0 %) | 208 (28.0 %) |
| complex | 1,451 | 747 (51.5 %) | 704 (48.5 %) |
| reasoning | 1,474 | 498 (33.8 %) | 976 (66.2 %) |
| **all** | **4,412** | **2,406 (54.5 %)** | **2,006 (45.5 %)** |

**The local model couldn't write hard prompts on demand.** Of the 1,474 prompts it wrote as reasoning, the relabeller called 549 reasoning and 537 medium. A typical one: *"Getting `OperationalError: (1215, 'Cannot add foreign key constraint')` when running a migration. Any ideas?"* The generator's note says it "requires reasoning about database constraints and migration logic". Haiku and Opus both called it medium.

That's why there is a second round: the script asked again for complex and reasoning with stricter hints (the reasoning one ends "Not a request to explain a known concept or compare popular tools"). Agreement on reasoning went from 28.9 % in round 1 to 38.7 % in round 2, and on complex from 44.8 % to 58.3 %. Better, and most reasoning prompts were still disputed. The generator wrote 1,474 prompts as reasoning, and the labelled set ended with 505 reasoning prompts.

**The adjudicator mostly sided with the relabeller.** Opus chose the relabeller's Tier in 1,516 of the 2,006 disputes (75.6 %) and the generator's in 360 (17.9 %). The two groups share 58 prompts where both had named the same Tier but the relabeller wasn't confident. In the other 188, Opus chose a third Tier.

**And it was confident on exactly half**: 1,003 of 2,006. Some of the unsure ones are a pasted error with no question at all, such as a bare `java.lang.NullPointerException` stack trace. Is that simple or medium? The Tier definitions describe the work an answer needs, and a stack trace alone doesn't state the ask.

## Training, and a decision I reversed the same day

The labelled prompts were split by Tier: 100 held out for eval, the rest 90/10 into train and validation. Eval mixes agreed prompts (319) and confidently adjudicated ones (81), so it isn't only the easy cases.

What about the 1,003 unsure verdicts? At 10:42 on 2026-10-06 I committed the first answer: they train but never measure. Three and a half hours later I committed the opposite:

| Training set | Val accuracy | Eval accuracy |
|---|---|---|
| confident labels + 1,003 unsure | 79.2 % | 79.3 % |
| **confident labels only (2,706)** | **82.2 %** | **80.0 %** |

So 37 % more training prompts made the classifier worse on both sets, and the unsure prompts are now set aside. The plausible reading is that a label an adjudicator isn't sure of is noise. But I chose between the two rows after seeing both columns, and the second column is the eval set. The moment I used it to choose, it stopped being held out.

## Results: 80.0 %, and what's inside it

Eval, 400 prompts, 100 per Tier: **accuracy 80.0 %, macro-F1 0.8034**. The target written into the task was at least 80 %.

| Tier | Recall | Precision | F1 |
|---|---|---|---|
| simple | 0.82 | 0.891 | 0.854 |
| medium | 0.77 | 0.647 | 0.703 |
| complex | 0.76 | 0.792 | 0.776 |
| reasoning | 0.85 | 0.914 | 0.881 |

| True ↓ / predicted → | simple | medium | complex | reasoning |
|---|---|---|---|---|
| simple | **82** | 16 | 2 | 0 |
| medium | 7 | **77** | 10 | 6 |
| complex | 2 | 20 | **76** | 2 |
| reasoning | 1 | 6 | 8 | **85** |

**Medium is the sink.** The classifier predicted medium 119 times and was right 77 times. The 42 wrong ones are more than half of its 80 errors.

**My notes say "almost every error is a neighbouring Tier". The matrix says 63 of 80.** The other 17 (21 %) are two or three Tiers away, including 6 medium prompts sent to reasoning, 6 reasoning prompts sent to medium and one sent to simple. In 44 of the 80 errors the predicted Tier is lower than the label; in 36 it is higher.

**Latency** on an Apple M4 Pro, 2 threads, one request at a time: p50 7.3 ms, p95 20.9 ms, over 210 requests (200 eval prompts plus 10 synthetic inputs that fill all 512 tokens). That's mostly the latency of short prompts: the median prompt in the dataset has 208 characters. My task notes record a full 512-token input at about 70 ms natively and about 175 ms in a Linux container on the same laptop. The target is a p95 of at most 800 ms on a c7i.xlarge, and I have never measured it there.

## What the 80 % doesn't tell you

1. **It was selected on the eval set.** With 320 of 400 correct, the 95 % Wilson interval is 75.8 % to 83.6 %. The 0.7-point gap between the two training choices is about three prompts, well inside that interval. "Meets the 80 % target" is true by the width of one prompt.
2. **Train and eval come from the same generator and the same grid.** Exact duplicates are removed (a prompt's ID is a hash of its normalised text), but nothing checks for near-duplicates. Two prompts from the same cell, one in train and one in eval, can be the same idea in different words.
3. **The labels are models' labels.** The pipeline writes a 150-row sample for me to review: 25 confident prompts per Tier and 50 unsure ones. My task notes say it "came back without corrections". The review file in the repo has no recorded corrections or labels: its `owner_tier` column is empty in all 150 rows. Either way, the labels come from agreement between language models, with at most a 150-row human check behind them.
4. **Eval leaves out the hard cases by construction.** The 1,003 prompts the adjudicator wasn't sure of are 22.7 % of the data. Real traffic won't leave its ambiguous prompts out.
5. **The head was trained on single prompts.** When it serves a conversation, the gateway also sends the earlier turns. No training or eval row has that context.
6. **The validation curve was still rising.** Macro-F1 on validation rose with every step of the L2 grid, from 0.7604 to 0.8201, and the chosen value is the grid's largest. I didn't try a larger one.
7. **The gateway has never called this classifier.** Locally the router service runs and an end-to-end script checks it, but the gateway's configuration points at a mock that answers with the Tier the test asks for.
8. **Nothing measures what the router is for.** The task that compares a pilot Organization's Spend per request before and after is open, and nothing checks whether a prompt sent to a cheaper Model got a good enough answer. I can't claim this router saves money or preserves quality.

What the synthetic labels did buy: a reproducible pipeline, a classifier whose errors I can read in a table, a measurement of where my own Tier definitions are ambiguous, and a baseline to beat when real, consented traffic exists.

## The rest of the gateway, briefly

The data plane is a first-party Go streaming reverse proxy. Three decisions shape it.

**It never translates between protocols.** Anthropic Messages requests go only to upstreams that speak Anthropic's API, OpenAI requests only to OpenAI-compatible ones, and bodies are forwarded byte for byte apart from the `model` field. That keeps `cache_control`, which prompt caching depends on, intact.

**One fixed pipeline of 13 steps**: request ID, authenticate, load the Member's context, resolve the Model (including `auto`), check the Profile, look up the price, admission hook, choose the upstream, forward and stream, extract usage, meter, settle hook, emit the Request Log record. Tokens come from Zitadel, which federates each Organization's Google or Microsoft sign-in, so the gateway validates a single issuer.

**Money is integer micro-dollars everywhere.** Quota is reserve-then-settle: a Lua script in Valkey checks the Member's Quota and the Organization's cap and reserves an upper-bound estimate in one atomic step, and a second script settles the real Spend. An exhausted Quota returns HTTP 403, not 429, because, by my design notes, Claude Code and Codex retry 429s automatically and a refusal would become a storm of retries. Each request's record goes through SQS to a daily-partitioned Postgres table; if the queue is unreachable, the gateway buffers 10,000 records per pod and then reports unready instead of dropping one.

All of it runs on a laptop: kind for Kubernetes, floci emulating the AWS APIs, and a mock provider that streams canned Anthropic and OpenAI responses with fault injection. An Organization can also plug in a hosted classifier (Jev, from TypeSafe AI) on its own key; that path is tested against a stub only.

## Local load tests: the worst number measured the emulator

Streamed requests with k6, straight to the mock and then through the gateway:

| Run | Path | Requests | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 20 streams, 10 s | direct to mock | 127,806 | 1.37 ms | 3.47 ms | 4.62 ms |
| 20 streams, 10 s | through gateway | 11,119 | 1.97 ms | 76 ms | 259 ms |
| 500 streams, 3 s | direct to mock | 74,983 | 13.1 ms | 53 ms | 77 ms |
| 500 streams, 3 s | through gateway | 3,740 | 37 ms | 16.9 s | 29.4 s |

A p99 of 29.4 s looks like a broken gateway. It's the emulator's SQS: in these runs floci accepted a Request Log batch of 10 in 1.1 s, and in about 8 s on the KMS-encrypted queue with a backlog, which caps local delivery at roughly 30 records a second. The buffer fills in seconds, and the gateway then does what it was designed to do: report unready and wait rather than drop a record. At 20 streams the median overhead was about 0.6 ms.

The runs still led to two fixes. One sender became 16 concurrent ones. And the buffer now drains on shutdown, within a 45 s grace period; before, a stopping pod could exit with records still buffered.

The MCP proxy's first runs were worse, and that was the gateway's own fault. At 20 tool calls a second the p95 was 2 to 10 s, and at 100 the pod was OOMKilled. A goroutine profile showed almost every call waiting on an S3 upload. Uploads moved off the request path and upstream connections were pooled; at 100 calls a second the gateway then added 0.7 ms at p95 (2.10 ms against 1.39 ms direct).

For `auto`, at 50 requests a second, the p95 went from 3.88 ms for a named Model to 9.71 ms: about 6 ms for the classification path, against a mock router that answers at once. The p99 went from 12.0 ms to 101.6 ms. The real classifier's inference time isn't in either number.

None of this says the gateway is fast in production. The targets (a p99 overhead under 25 ms to the first byte at 500 streams in staging, at most 300 ms added by `auto` at p95 with the real Router deployed) are both still open, and there is no staging run.

## Where the project actually is

The repo has 178 commits over 9 active days, from 2026-09-24 to 2026-10-06. Of those, 39 are merges, and all 139 others carry a coding agent's co-author trailer. It was built spec first, with OpenSpec: 19 changes, 242 tasks checked and 59 open. Most of the open ones wait for the same thing, a real environment to verify in. The environment runbook says it plainly: "planned, not executed. The AWS account doesn't exist yet and nothing has been applied."

Real Claude Code and Codex CLI sessions ran through the local gateway, against the mock provider. No real provider has answered a request through the gateway. And the project's own README still says "planning. Nothing is implemented yet", which is stale in the other direction.

## What I'd tell a team building this

1. **Read the licence before you design around a model.** I found mine, as I read it, unusable in a hosted product after the gateway side was already built against that model's interface.
2. **Use label disagreement as a measurement.** Two model families agreed on 54.5 % of the prompts, and the rate per Tier (84.2 % down to 33.8 %) showed where my Tier definitions are vague before any classifier existed.
3. **Don't trust a generator to hit a hard class.** Asked for reasoning prompts, the local model wrote prompts that another model called medium about as often as reasoning. A stricter second round raised agreement by about 10 points. It didn't fix it.
4. **More labels can be worse labels.** Adding 1,003 unsure verdicts cost 3 points on validation. Try it both ways, and decide on validation only.
5. **Write down the moment you looked at the eval set.** Mine is a same-day reversal, visible in two commits. The number is still useful. It just isn't what "held-out" promises.
6. **Compute the claim from the matrix.** "Almost every error is a neighbouring Tier" was my own note. The matrix says 79 %.
7. **Ask what your slowest local number is measuring.** Mine measured an emulator's queue. The same runs led to two real fixes, so run the test anyway.
8. **Keep "built" and "verified where it will run" apart.** A synthetic eval and a local load test are worth having. They aren't a pilot.

---

*Project: [github.com/ricardocunha/keelgw](https://github.com/ricardocunha/keelgw) (Keel Gateway). The router is in `router/`, its metrics in `router/model/metrics.json`, the load tests in `gateway/loadtest/RESULTS.md`. Models: intfloat/multilingual-e5-small (MIT per its model card) for embeddings; Qwen2.5-Coder-32B (Apache-2.0 per my project notes) on Ollama for generation; Claude Haiku 4.5 and Claude Opus 5.5 for labels. Statements about other projects (Arch-Router, RouteLLM, Jev, Zitadel, floci, the licences above, and how Claude Code and Codex retry) are my notes as recorded in the project's documents in September and October 2026; check them before relying on them. Drafts and the source of every number: [github.com/ricardocunha/ensaios › articles/2027-02-keelgw-ai-gateway](https://github.com/ricardocunha/ensaios/tree/main/articles/2027-02-keelgw-ai-gateway).*

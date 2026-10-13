# Sources for every number and claim

Where each number and factual claim in the drafts comes from, so the drafts can be reviewed before publishing.

- **Repo:** [github.com/ricardocunha/keelgw](https://github.com/ricardocunha/keelgw), read at commit `4fc8d21` (branch `main`, 2026-10-06). Paths and line numbers below are at that commit.
- **Not read:** anything git-ignored (`router/data/*.log`, `router/data/state.json`, `router/data/generated.jsonl`, `.local/`, `mise.local.toml`).
- **"derived"** means I computed the value from tracked files; the method is in [Derivations](#derivations).
- The drafts hold no `VERIFY` or `RESULT` placeholders. What I could not verify is listed in [Not verified](#not-verified-and-how-the-drafts-word-it).

## Router: design and decision

| Claim in the drafts | Source |
|---|---|
| keelgw is a multi-tenant AI gateway for small businesses: which Models each Member may reach, through which Clients (Claude Code, Claude Cowork, Codex), at what USD Spend, on the Organization's own provider accounts | `README.md:3`; `CONTEXT.md:3` |
| `auto` is a virtual Model; a Router assigns one of four Tiers (simple, medium, complex, reasoning); the Profile's Tier Map says which allowed Model serves each Tier | `CONTEXT.md:93-103` |
| The classifier returns only a Tier, never a Model name, so swapping it never changes what a Member can reach | `openspec/changes/add-auto-model-routing/design.md:21` (D1) |
| The four Tier definitions (paraphrased, shortened) | `router/dataset.py:38-45` |
| The gateway and the training script share the definitions; a test fails if they drift | `router/README.md:98`; `router/dataset.py:36-37` |
| Built-in Router timeout 1,500 ms, then the Profile's fallback Tier; classification never refuses a request | `design.md:37` (D4); `gateway/internal/autoroute/autoroute.go:66` |
| First choice was Arch-Router-1.5B, a generative model matching a prompt against natural-language policies, "on the belief that it was Apache-2.0" (quote) | `design.md:27`; the original D2 text is in the diff of commit `772e482` |
| Blocker recorded 2026-09-30: Katanemo licence, separate commercial licence from DigitalOcean for any commercial use, including offering the model as a service | `openspec/changes/add-auto-model-routing/tasks.md:41`; commit `cb7f861` (2026-09-30) added that line |
| RouteLLM was the fallback candidate | original D2 text, removed in commit `772e482` ("RouteLLM stays the fallback candidate") |
| RouteLLM: binary strong/weak; recommended routers call OpenAI's embeddings API for every prompt; self-hosted checkpoints carry no licence; code is Apache-2.0 | `design.md:25`, `design.md:28`; `tasks.md:42` |
| Decision on 2026-10-03 to train an own four-Tier classifier: no GPU, nothing sent outside, every part under a shippable licence | `design.md:31`; `tasks.md:42`; commit `772e482` |
| The gateway side was already built against Arch-Router's interface when the licence blocker was found | `tasks.md:40` (2026-09-28 note: "the mock answers in Arch-Router's format"); diff of `772e482` ("built against Arch-Router's interface") |
| "about 26 hours from the first commit of the data-generation script to the committed model" | derived (D1): commits `1e50dc6` (2026-10-05 11:56 -0300, the first version of `router/dataset.py`) and `e522c85` (2026-10-06 14:15 -0300) |

## Router: classifier

| Claim | Source |
|---|---|
| `intfloat/multilingual-e5-small`, MIT per its model card's licence metadata, pinned to a Hugging Face revision with sha256 checks | `router/README.md:7`; `design.md:60` |
| Chosen over an English-only candidate because Members write in other languages | `design.md:60` |
| ONNX export on ONNX Runtime, CPU, no torch | `router/README.md:8` |
| 384-dimension embedding | `router/classifier.py:27` |
| Head: multinomial logistic regression, four outputs, class-balanced weights, L2 picked on val by macro-F1, serving is `softmax(Wx + b)` | `router/README.md:10`; `router/train.py:119-146`, `:173-187` |
| Head file "about 21 KB" | derived (D2): `router/model/head.json` is 21,268 bytes. `router/README.md:10` says "about 30 KB" (see Conflicts) |
| Input: latest user turn plus earlier turns, at most 8,000 characters | `gateway/internal/autoroute/prompt.go:11`; `design.md:71`; `router/README.md:14` |
| The model reads 512 tokens; latest turn first, earlier turns in the room left | `router/classifier.py:33-37`, `:93-106`; `router/README.md:14-18` |
| The service never logs prompt text | `router/README.md:36` |
| Image about 0.76 GB, model 487 MB | `tasks.md:57` |

## Router: data

| Claim | Source |
|---|---|
| Generator: Qwen2.5-Coder-32B on Ollama, local | `router/dataset.py:81`; `router/README.md:75`; commit `da2256d` |
| Grid: Tier × 12 stacks × 4 shapes, 16 prompts per request | `router/dataset.py:47-60` (stacks), `:62-67` (shapes), `:72`, `:131-141` |
| Round 1 = 192 cells, round 2 = 96 cells (complex and reasoning again), 288 in all | derived (D3) from `dataset.py:131-141`; `router/data/generated-raw.jsonl` has 288 lines, 96 with a `-r2` ID |
| A third of the cells ask for 4 of 16 prompts in Portuguese, Spanish, German or French | `dataset.py:70`, `:139`, `:216`; derived (D3): 16 of the 48 stack × shape pairs satisfy `(i + j) % 3 == 0` |
| Quote: prompts "a developer types into a coding assistant" | `dataset.py:145` |
| Each request asks for at least three prompts that would fool a length-based guess | `dataset.py:159-160` |
| Round 2 exists because the first round's complex and reasoning prompts were often judged medium; the hint quote | `dataset.py:119-128`; `tasks.md:65`; commit `3a8e9aa` |
| 4,412 distinct prompts | `tasks.md:65`; commit `e522c85` message; derived (D4): `router/data/prompts.jsonl` has 4,412 rows, 4,412 distinct IDs |
| Relabel: Claude Haiku 4.5, Message Batches API, blind to the Tier, 20 shuffled prompts per request, with a `confident` flag | `dataset.py:84`, `:73`, `:180-186`, `:451`; `router/README.md:76` |
| "Agreed" = relabel equals the Tier written for and the relabel is confident | `dataset.py:534` |
| Adjudication: Claude Opus 5.5 sees both suggestions and is told either may be wrong | `dataset.py:88`, `:469-475`, `:482`; commit `3a8e9aa` |
| 2,006 disputes; total API spend $1.88 | `tasks.md:66`; commit `e522c85` message; derived (D4): 2,006 rows with an adjudication |
| The script refuses a paid phase that would pass its budget; default 3 dollars | `dataset.py:320-321`, `:631` |
| Splits: train 2,706, val 303, eval 400 (100 per Tier); 1,003 unsure set aside | `router/model/metrics.json:3-22`; `tasks.md:67-68`; derived (D4) |
| 3,409 labelled prompts (2,406 agreed + 1,003 confidently adjudicated) | derived (D4) |
| Agreement table: per Tier written for (745 / 742 / 1,451 / 1,474), agreed 627 / 534 / 747 / 498, disputed 118 / 208 / 704 / 976, and the percentages; 2,406 of 4,412 = 54.5 % | derived (D4) |
| Of 1,474 prompts written as reasoning, the relabeller called 549 reasoning and 537 medium | derived (D4) |
| Example prompt (`OperationalError: (1215, ...)`), its generator note, relabelled medium, adjudicated medium with confidence | `router/data/prompts.jsonl`, row `id` `d181cfa494beba32` |
| Round 1 vs round 2 agreement: reasoning 28.9 % → 38.7 %, complex 44.8 % → 58.3 % | derived (D5) |
| The generator wrote 1,474 prompts as reasoning; the labelled set has 505 reasoning prompts | derived (D4): 1,474 distinct prompts with `generated_tier == "reasoning"` (96 cells × 16 = 1,536 requested, 1,480 returned, 1,474 after deduplication); 505 rows with `tier == "reasoning"` in train, val or eval (498 agreed, 5 written as reasoning and adjudicated reasoning, 2 written as complex) |
| Opus chose the relabeller's Tier in 1,516 of 2,006 (75.6 %), the generator's in 360 (17.9 %), both in 58, neither in 188 | derived (D6) |
| Opus was confident on 1,003 of 2,006 | `tasks.md:67`; derived (D4) |
| Unsure example: a bare `java.lang.NullPointerException` stack trace with no question | `router/data/prompts.jsonl`, row `id` `0783dd35b6c65101` (`split` `unsure`) |
| Eval mixes 319 agreed and 81 confidently adjudicated prompts | derived (D4); the intent is in `dataset.py:555-556` |

## Router: training, results, caveats

| Claim | Source |
|---|---|
| Split rule: 100 per Tier for eval, rest 90/10 train/val | `dataset.py:553-573`; `router/README.md:97` |
| Commit at 10:42 on 2026-10-06: unsure adjudications train but never measure | commit `a42e86f` (2026-10-06 10:42:23 -0300) |
| Reversed three and a half hours later | commit `e522c85` (2026-10-06 14:15:05 -0300); `dataset.py:76-78` (`TRAIN_ON_UNSURE = False`); derived (D1) |
| With unsure: 79.2 % val, 79.3 % eval. Without: 82.2 % and 80.0 % | `tasks.md:67`; the second pair also in `metrics.json:26`, `:98` |
| "37 % more training prompts" | derived (D7): 1,003 / 2,706 |
| Both columns were seen before choosing, and the second is the eval set | `dataset.py:76-77` ("scored higher on both val and eval") |
| Eval n = 400, accuracy 0.80, macro-F1 0.8034 | `metrics.json:96-99` |
| Per-Tier recall 0.82 / 0.77 / 0.76 / 0.85 (the file's `accuracy` field is recall, see `train.py:159-163`), precision 0.8913 / 0.6471 / 0.7917 / 0.914, F1 0.8542 / 0.7032 / 0.7755 / 0.8808 (rounded to three decimals in the drafts) | `metrics.json:100-125` |
| Confusion matrix | `metrics.json:126-158` |
| Target: at least 80 % accuracy and p95 at most 800 ms on a c7i.xlarge; not measured there | `tasks.md:11`, `:72`; `metrics.json:176-180`; `router/README.md:54`, `:62` |
| Medium predicted 119 times, right 77; the 42 wrong ones are more than half of the 80 errors (52.5 %) | derived (D8) |
| 80 errors: 63 adjacent, 16 two Tiers apart, 1 three apart; 44 predicted lower than the label, 36 higher; the named cells | derived (D8) |
| Quote "almost every error is a neighbouring Tier" | `tasks.md:69` |
| Latency p50 7.3 ms, p95 20.9 ms, n = 210, Apple M4 Pro, 2 threads, one request at a time | `metrics.json:161-173` |
| The 210 = 200 eval prompts + 10 synthetic inputs that fill 512 tokens | `router/train.py:262-265`, `:248` |
| Median prompt length 208 characters | derived (D4) |
| A full 512-token input: about 70 ms natively, about 175 ms in a Linux container on the same laptop | `tasks.md:62` |
| 95 % Wilson interval for 320 of 400: 75.8 % to 83.6 % | derived (D9) |
| The 0.7-point gap is about three prompts | derived (D9): 0.7 % of 400 = 2.8 |
| Exact duplicates are removed (ID = hash of the normalised text); nothing checks near-duplicates | `dataset.py:257-258`, `:425-430`; no similarity check exists in `router/dataset.py` or `router/train.py` |
| Review sample: 150 rows, 25 confident per Tier and 50 unsure | `dataset.py:75`, `:579-586`; derived (D10) |
| Quote "came back without corrections" | `tasks.md:71` |
| The review file has no recorded corrections or labels: `owner_tier` is empty in all 150 rows | derived (D10) from `router/data/review.csv` |
| Unsure prompts are 22.7 % of the data | derived (D7): 1,003 / 4,412 |
| Training and eval rows are single prompts with no earlier turns | `router/train.py:226` (embeds `r["text"]` only); `router/classifier.py:76-77` (context defaults to empty) |
| Val macro-F1 rose with every L2 step, 0.7604 to 0.8201; the chosen value is the grid's largest | `metrics.json:23`, `:89-95`; `router/train.py:43` |
| The gateway has never called the real classifier: the local gateway points at the mock; a separate e2e script checks the real service | `deploy/envs/local/gateway.values.yaml:18-20`; `router/README.md:38`; `design.md:69`; `tasks.md:77` |
| The mock answers with the Tier the test asks for | `design.md:69` (`#tier:<tier>` directive) |
| No measurement of Spend saved: task 5.3 is open; no answer-quality check exists | `tasks.md:33`, `:48` |
| A hosted classifier (Jev, TypeSafe AI) on the Organization's own key, tested against a stub only | `CONTEXT.md:109-110`; `design.md:3`, `:34`; `tasks.md:6`, `:39` |

## Gateway

| Claim | Source |
|---|---|
| First-party Go streaming reverse proxy | ADR 0003 (`docs/adr/0003-*.md`) `:3` |
| Never translates between protocols; bodies forwarded byte for byte apart from `model`; `cache_control` kept intact | ADR 0003 `:12-13`; `openspec/changes/add-gateway-core/design.md:20`, `:138` |
| Pipeline of 13 steps (the list) | `add-gateway-core/design.md:40-54` |
| Zitadel federates each Organization's Google or Microsoft sign-in; the gateway validates one issuer | `docs/adr/0004-zitadel-as-platform-authorization-server.md:3` |
| Money as integer micro-dollars everywhere | `docs/roadmap.md:92`; `add-gateway-core/design.md:74-76` |
| Reserve-then-settle Quota: one Lua script in Valkey checks the Member's Quota and the Org Cap and reserves an upper-bound estimate atomically; a second settles | `openspec/changes/add-quota-enforcement/design.md:44-64`; `deploy/apps/valkey/values.yaml:1` |
| Exhausted Quota returns 403, not 429, because (as the design notes say) Claude Code and Codex retry 429s automatically | `add-quota-enforcement/design.md:99-106`; `docs/roadmap.md:83` |
| Request Log through SQS to a daily-partitioned Postgres table; 10,000-record buffer per pod, then unready, never dropping | `add-gateway-core/design.md:93-96`, `:145` |
| Local stack: kind, floci emulating AWS APIs, a mock provider with canned Anthropic and OpenAI responses and fault injection | `docs/adr/0006-local-dev-on-kind-and-floci-with-split-infra-layers.md:3`, `:7`; `docs/local-development.md:3`, `:105-123` |
| Streaming load test table (all eight rows) | `gateway/loadtest/RESULTS.md:7-12` |
| floci's SQS: a batch of 10 in 1.1 s, about 8 s on the KMS-encrypted queue with a backlog, roughly 30 records a second; the wait is the long tail | `RESULTS.md:14-16` |
| Median overhead about 0.6 ms at 20 streams | `RESULTS.md:17` |
| Two fixes ("Two fixes came out of these runs"): 16 concurrent senders instead of one; buffer drains on shutdown within a 45 s grace period | `RESULTS.md:18-20`; commit `f3bda53` |
| MCP: first runs p95 2 to 10 s at 20 calls/s, OOMKilled at 100 calls/s; goroutine profile showed calls waiting on S3 PutObject | `RESULTS.md:35` |
| MCP fixes: uploads off the request path, pooled upstream connections | `RESULTS.md:37-38`; commit `8f2e550` |
| MCP after: p95 2.10 ms through the gateway vs 1.39 ms direct, +0.7 ms, at 100 calls/s | `RESULTS.md:30-33` |
| `auto` at 50 requests/s: p95 3.88 ms (named Model) vs 9.71 ms; p99 11.99 ms vs 101.6 ms; about 6 ms; the mock stands in for the Router | `RESULTS.md:47-54`, `:58` |
| Targets: p99 overhead under 25 ms to first byte at 500 streams, against staging; at most 300 ms added by `auto` at p95, to be measured once the real Router is deployed; both open | `RESULTS.md:22`, `:58`; `add-gateway-core/design.md:22`; `add-auto-model-routing/tasks.md:32` |

## Project status

| Claim | Source |
|---|---|
| 178 commits, 9 active days, 2026-09-24 to 2026-10-06 | derived (D11) |
| 39 of the 178 commits are merges; all 139 others carry a coding agent's co-author trailer | derived (D11) |
| 19 OpenSpec changes; 242 tasks checked, 59 open | derived (D12) |
| "Most of the open ones wait for a real environment" | derived (D12): 41 of the 59 open tasks name staging, AWS, prod, a pilot, a live or real system, or a deployment (keyword match, a lower bound) |
| Quote: "planned, not executed. The AWS account doesn't exist yet and nothing has been applied" | `docs/runbooks/environment-buildout.md:5` |
| Real Claude Code and Codex CLI sessions ran through the local gateway against the mock | `openspec/changes/add-gateway-core/tasks.md:20`; commit `12f8357` |
| README still says "planning. Nothing is implemented yet." | `README.md:5` |
| No real provider has answered a request through the gateway; no customer | live-provider tests are open (`add-gateway-core/tasks.md:18-19`, `add-gateway-core/design.md:154`); pilot tasks open (`add-auto-model-routing/tasks.md:48`); see Not verified, item 1 |

## Derivations

All run from the keelgw repo root on tracked files, with `python3 -I`.

- **D1. Commit times.** `git log -1 --format=%ad --date=iso <hash>` for `1e50dc6`, `a42e86f`, `e522c85`. 2026-10-05 11:56:41 to 2026-10-06 14:15:05 is 26 h 18 min. 10:42:23 to 14:15:05 is 3 h 33 min.
- **D2. Head size.** `ls -l router/model/head.json` gives 21,268 bytes.
- **D3. Grid.** Round 1 is 4 Tiers × 12 stacks × 4 shapes = 192 requests; round 2 is 2 Tiers × 12 × 4 = 96. Language cells: pairs `(i, j)` with `i` in 0..11, `j` in 0..3 and `(i + j) % 3 == 0`: 16 of 48. `wc -l router/data/generated-raw.jsonl` gives 288; `grep -c -- '-r2"' router/data/generated-raw.jsonl` gives 96.
- **D4. Dataset counts.** Load `router/data/prompts.jsonl` as one JSON object per line (`rows`). Then: `len(rows)`; `Counter(r["split"])`; for each `t` in the four Tiers, `g = [r for r in rows if r["generated_tier"] == t]`, agreed = `sum(r["agreed"] for r in g)`, disputed = `sum(r["adjudicated"] is not None for r in g)`; overall agreed = 2,406; `sum(r["adj_confident"] for r in rows if r["adjudicated"])` = 1,003; relabel distribution of the prompts written as reasoning = `Counter(r["relabel"] for r in g)` = reasoning 549, medium 537, complex 315, simple 73; eval rows with `agreed` = 319, the other 81 have a confident adjudication; reasoning rows in train, val or eval = 505; median of `len(r["text"])` = 208. Note: 2,504 prompts have the same Tier from generator and relabeller, but 98 of those relabels were not confident, so they count as disputed; 2,406 is the figure the pipeline uses.
- **D5. Rounds.** `prompts.jsonl` has no round field. For each line of `router/data/generated-raw.jsonl`, parse `content` as JSON, and for each prompt compute the ID as `sha256(" ".join(text.lower().split()))[:16]` (the rule in `dataset.py:257-258`); the round is 2 if `custom_id` ends in `-r2`, else 1; the first occurrence of an ID wins (as in `dataset.py:425-430`). All 4,412 IDs map. Agreed share by round and Tier written for: round 1 simple 627/745, medium 534/742, complex 328/732 (44.8 %), reasoning 214/740 (28.9 %); round 2 complex 419/719 (58.3 %), reasoning 284/734 (38.7 %).
- **D6. Adjudicator's side.** Over the 2,006 rows with `adjudicated`: `adjudicated == relabel` in 1,516; `adjudicated == generated_tier` in 360; both true in 58 (same Tier from both, relabel not confident); neither in 188. 1,516 + 360 − 58 + 188 = 2,006.
- **D7. Ratios.** 1,003 / 2,706 = 37.1 %. 1,003 / 4,412 = 22.7 %. 2,006 / 4,412 = 45.5 %. The "37 % more training prompts" assumes the earlier run's confident train split was the same 2,706 rows; the split code and seed for confident prompts are unchanged between `a42e86f` and `e522c85` (see their diff of `assign_splits`).
- **D8. Confusion matrix.** From `metrics.json` `eval.confusion.matrix` `M` (rows true, columns predicted, order simple, medium, complex, reasoning): errors = sum of off-diagonal cells = 80; adjacent = cells with `abs(i - j) == 1` = 16 + 7 + 10 + 20 + 2 + 8 = 63; two apart = 2 + 6 + 2 + 6 = 16; three apart = 0 + 1 = 1; predicted lower than the label (`j < i`) = 44; higher = 36; column sums = 92, 119, 96, 93. 63 / 80 = 78.75 %.
- **D9. Wilson interval.** `p = 320/400`, `z = 1.96`, centre `(p + z²/2n) / (1 + z²/n)`, half-width `z·sqrt(p(1−p)/n + z²/4n²) / (1 + z²/n)`: 0.7580 to 0.8363. (The normal approximation gives 0.7608 to 0.8392.) 79.3 % of 400 is about 317 prompts; 80.0 % is 320. The two runs share one eval set, so this interval describes the sampling uncertainty of one score; it is not a paired test of the difference.
- **D10. Review file.** `csv.DictReader(open("router/data/review.csv"))`: 150 rows; `owner_tier.strip()` is empty in all 150; `label` counts: medium 47, complex 42, simple 34, reasoning 27 (100 confident rows at 25 per Tier plus 50 unsure).
- **D11. Commits.** `git log --oneline | wc -l` = 178 (39 of them merges, `git log --merges --oneline | wc -l`). `git log --format=%ad --date=short | sort -u` gives 9 dates: 2026-09-24, -25, -28, -29, -30, 2026-10-02, -03, -05, -06. `git log --format=%b | grep -c 'Co-Authored-By: Claude'` = 139; none of the 39 merges has the trailer, so every non-merge commit does.
- **D12. OpenSpec.** 14 active changes in `openspec/changes/` plus 5 in `openspec/changes/archive/` = 19. `cat openspec/changes/add-*/tasks.md openspec/changes/archive/*/tasks.md | grep -c '^- \[x\]'` = 242; the same with `'^- \[ \]'` = 59. Open tasks in active changes (58 of the 59; one is in an archived change) matching `staging|AWS|prod\b|pilot|real |live|c7i|ArgoCD|EKS|deploy` (case-insensitive): 41. Several of the 17 that don't match are also AWS infrastructure tasks (state bucket, VPC, RDS, ECR, CloudFront).

## Conflicts and stale statements in the project's docs, and the value used

| Topic | What the repo says | Used in the drafts |
|---|---|---|
| Router latency | Three figures for three sample mixes: `router/README.md:65-67` (short prompt 6 to 7 ms; full 512-token prompt 66 ms p50 / 72 ms p95 with 2 threads); `tasks.md:62` (p50 10 ms, p95 49 ms over eval prompts plus full inputs; about 70 ms and about 175 ms for a full input); `metrics.json:161-173` (p50 7.3, p95 20.9, max 48.4 ms, n = 210) | `metrics.json` for the headline, with what the 210 requests are. The 70 ms and 175 ms figures are quoted once, attributed to the task notes. Note that the file's max (48.4 ms) is below the README's 66 ms for a full input, although 10 full inputs are in the sample; I did not resolve this |
| API cost | `router/README.md:76`: the relabel costs "about $1". `tasks.md:66` and commit `e522c85`: "$1.88 in total" (relabel plus adjudication) | $1.88, always as the total of both paid phases. The per-phase split is not in tracked files |
| "Almost every error is a neighbouring Tier" | `tasks.md:69` | The computed split: 63 of 80 adjacent, 17 not (D8) |
| Owner review | `tasks.md:71`: the 150-row sample "came back without corrections" | Quoted, then: "The review file in the repo has no recorded corrections or labels" (D10) |
| Head size | `router/README.md:10`: "about 30 KB" | "about 21 KB" (D2) |
| Project status | `README.md:5`: "planning. Nothing is implemented yet." | Mentioned as stale; the status comes from the OpenSpec task files and the runbook |
| Who reviews disputes | `router/dataset.py:6-8` (module docstring): disputed prompts "go to the owner for review" | The code path as built: Opus adjudicates (`dataset.py:502-518`) |
| Unsure labels | `router/dataset.py:538-539` (comment): "An unsure adjudication still trains" | The constant that decides it: `TRAIN_ON_UNSURE = False` (`dataset.py:76-78`) |
| Embedding model | `design.md:29` still lists BAAI/bge-small-en-v1.5 as the candidate | As built: multilingual-e5-small (`design.md:60`) |
| Task 2.2 state | `tasks.md:11` is unchecked; the head is trained and committed | Described as trained, with the c7i.xlarge measurement still open |
| Input size | `design.md:31` speaks of a 2,000-token tail; the model reads 512 tokens | Both stated: 8,000 characters sent, 512 tokens read |
| Counters store | `docs/roadmap.md:92`, `:101` say Redis; the quota design and the local deployment say Valkey | Valkey |
| Request Log partitions | `add-gateway-core/design.md:96` says `pg_partman`; as built, native daily partitions (`:145`) | "daily-partitioned Postgres table" |

## Not verified, and how the drafts word it

1. **"The gateway never sent a request to a real model provider, never served a customer."** The repo shows the live-provider and pilot tasks as open and says the AWS account doesn't exist. It cannot prove that no real key was ever tried locally (the local design allows a contributor to add one). The author should confirm before publishing. The data pipeline did call a real API (the Haiku and Opus labelling batches), so the drafts say "the gateway", and say so in the banner.
2. **The 79.2 % / 79.3 % run.** Only `tasks.md:67` records it; no metrics file from that run is tracked. Reproducing it needs `TRAIN_ON_UNSURE = True` and a retrain.
3. **$1.88.** From the task notes and a commit message. The spend ledger (`router/data/state.json`) is git-ignored and was not read.
4. **The budget actually passed to the paid phases.** Only the default (3 dollars) is in tracked code; the drafts say "3 dollars by default".
5. **How many prompts are not in English.** The `language` field in `prompts.jsonl` is the cell's language, set on all 16 prompts of a cell although only 4 were requested in it, so it over-counts. The drafts state only what the grid requested.
6. **How long generation took.** `router/README.md:75` says "a night on a laptop"; not used.
7. **Near-duplicates between train and eval.** Not measured. A normalised exact-match check (lower-case, punctuation stripped) finds none, which is expected since IDs already deduplicate; the drafts say nothing checks for near-duplicates.
8. **Whether the earlier run used the same val and eval rows.** Inferred from the code (same seed, same confident pool), not from an artifact.

## Third-party claims to re-verify before publishing

Each is stated in the drafts only as the project's documents record it, with the date.

| Claim | Where the repo records it | Used in |
|---|---|---|
| Arch-Router-1.5B (katanemo) is under the Katanemo licence, which requires a separate commercial licence from DigitalOcean for any commercial use, including offering the model as a service | `add-auto-model-routing/tasks.md:41` (2026-09-30); `design.md:27` | all articles, LinkedIn (as "as I read its licence") |
| RouteLLM: binary strong/weak routing; its recommended routers (`mf`, `sw_ranking`) call OpenAI's embeddings API for every prompt; the self-hosted checkpoints (`bert`, `causal_llm`) carry no licence; its code is Apache-2.0 | `design.md:25`, `:28`; `tasks.md:42` (2026-10-03) | full articles, Medium |
| intfloat/multilingual-e5-small: MIT per its model card's licence metadata; 384 dimensions; reads 512 tokens | `router/README.md:7`; `design.md:60` | all articles |
| Qwen2.5-Coder-32B is Apache-2.0 | `router/README.md:75` | footers (as "per my project notes") |
| Jev is a hosted classifier from TypeSafe AI, reached with the Organization's own key | `design.md:3`, `:34` | full articles (one sentence, no performance figures) |
| Claude Code and Codex retry HTTP 429 automatically | `add-quota-enforcement/design.md:106`; `docs/roadmap.md:83` | full articles, Medium (as "by my design notes") |
| Zitadel federates Google Workspace and Microsoft Entra sign-in as an OIDC authorization server | ADR 0004 `:3` | full articles |
| floci emulates AWS APIs; the SQS and S3 speeds are the project's own local measurements of it | ADR 0006 `:3`; `RESULTS.md:15`, `:41` | full articles, Medium |
| Prompt caching depends on `cache_control` passing through untouched | ADR 0003 `:13` | full articles |
| Model names "Claude Haiku 4.5" and "Claude Opus 5.5" | `router/README.md:76-78`; `dataset.py:84`, `:88` | everywhere |

Not used on purpose: any figure about Jev's published benchmark, any other gateway or tool the project's documents compare against, provider prices or AWS costs.

## Proofread 2026-10-09

An independent pass over all drafts against the keelgw repo at `4fc8d21`, tracked files only.

**Recomputed, all matching the drafts.** The dataset was rebuilt from `generated-raw.jsonl`, `relabels.jsonl` and `adjudications.jsonl` (IDs by the hash rule, first occurrence wins, round 1 before round 2) and compared with `prompts.jsonl`: same 4,412 IDs, no mismatch in Tier written for or relabel. From that rebuild: the per-Tier agreement table and 54.5 %; 549 / 537 (and 315 complex, 73 simple) for prompts written as reasoning; round 1 vs round 2 (214/740, 284/734, 328/732, 419/719); adjudicator 1,516 / 360 / 58 / 188; confident 1,003 of 2,006; splits 2,706 / 303 / 400 / 1,003; 505 reasoning prompts; eval 319 + 81; median length 208. From `metrics.json`: 63 / 16 / 1, 44 / 36, column sums, per-Tier precision and F1 recomputed from the matrix, the L2 curve. Wilson interval with z = 1.959964: 0.7580 to 0.8363. 1,003 / 2,706 = 37.1 %; 1,003 / 4,412 = 22.7 %. Latency sample 200 + 10 (`train.py:248`, `:265`). Commits 178 / 9 days / 139; 26 h 18 min and 3 h 33 min. OpenSpec 19 / 242 / 59 over the 19 tracked `tasks.md`. Both example prompts exist verbatim with the labels described. Every cell of the load-test table and every figure of that section against `gateway/loadtest/RESULTS.md`.

**Changed in the drafts.**

1. "I asked for 1,474 reasoning prompts" was wrong: 1,536 were requested and 1,474 distinct ones were written. Now "The generator wrote 1,474 prompts as reasoning". Full EN.
2. "Every number below comes from a laptop" and "never called a real model provider" overlooked the labelling batches, which called a real API. The banner now says "the keelgw gateway", "every measurement", and names the labelling batches. "No real provider has answered a request" gained "through the gateway". All articles and the README.
3. "When it's unsure, it says medium" had no support (nothing measures the classifier's confidence). Now: the 42 wrong medium predictions are more than half of the 80 errors. Full EN.
4. "139 of them carry a co-author trailer" is now "39 are merges, and all 139 others carry" it; the Medium version said "most".
5. The load tests "found two real problems / bugs" is now "led to two fixes", as `RESULTS.md` puts it. The targets sentence no longer says the 300 ms target "is for staging": the file says it waits for the real Router to be deployed.
6. "80.0 % on 400 held-out prompts" now says "synthetic" in the short version of every draft. "Agreed on 54.5 %" now says what agreed means (same Tier, relabeller confident) where the table isn't next to it; same-Tier agreement regardless of confidence is 2,504 (56.8 %) and is not used.
7. The Medium draft put "they train but never measure" in quotation marks; the commit subject is "unsure adjudications train but never measure". The marks are gone.
8. Third-party wording: the subtitle now carries "as I read its licence"; "A hosted gateway is exactly that" became conditional; the notes are dated "September and October 2026" (the Arch-Router note is from 2026-09-30); the 429 retry behaviour is attributed to the design notes and names Claude Code and Codex; Qwen's licence is "per my project notes"; the footers list every third-party project the notes cover.
9. Voice: "I asked again" (second round) is now "the script asked again", and the quoted hint is identified as the reasoning one, the only one that holds it. "Members write in other languages" is "will write" (there are no Members yet). "In production the gateway appends earlier turns" is "When it serves a conversation" (there is no production).
10. Caveat 3 no longer concludes that no human judged the labels: the record can't tell an unreviewed file from a review without corrections. It now says the labels come from agreement between models "with at most a 150-row human check behind them".
11. LinkedIn: "for $1.88" is "on $1.88 of API spend".
12. This file: the rows for the items above, and the names of tools the drafts don't discuss were removed from a file path and from the "not used" line.

**Left for the author.** Whether he reviewed the 150-row sample himself; whether he read the Arch-Router licence himself on 2026-09-30 (the drafts say "as I read"); whether a real provider key was ever tried locally; the title's "for $1.88" (API spend for labels only; the article says so in its first bullet). Nothing in `router/` or `openspec/changes/add-auto-model-routing/` records a check of whether the provider's terms allow training a classifier on Claude Haiku 4.5 and Claude Opus 5.5 labels; the drafts make no claim either way.

## Author decisions, 2026-10-09

Applied to the drafts after the proofread, from the author's answers. No project code was touched.

- **Claude labels and provider terms:** named openly. New paragraph "One thing I haven't checked" after the cost paragraph (EN), caveat 9 (EN) and caveat 7 (Medium). No claim either way about what the terms allow. The reference to "an earlier article in this series" is the CNH article (`articles/2026-10-cnh-ocr-smithtune`, section "Then I changed the Teacher"). **To settle before publishing:** read Anthropic's terms on training with model outputs.
- **150-row label review:** the author has not reviewed the sample yet. Caveat 3 now says so in every version; the task note "came back without corrections" (`openspec/changes/add-auto-model-routing/tasks.md:71`) is no longer quoted. The project note itself is unchanged and still says that.
- **Arch-Router licence:** the note of 2026-09-30 was found by the coding agent, not read by the author. "As I read its licence" became "by my project notes" everywhere (subtitles, intro, body, lesson 1, LinkedIn, README). **To do before publishing:** the author reads the licence himself.
- **Real provider through the gateway:** author confirms never. Banner unchanged.
- **Earlier `auto` load-test run (2.2 s p95, 586 dropped):** left out by the author's choice.
- **Length:** kept.

## Diagrams, 2026-10-09

The two ASCII diagrams in `article-en.md` were replaced by images made with archify (MIT): `images/classifier.en.{svg,png}` and `images/labelling.en.{svg,png}`, with their sources in `images/diagrams/*.dataflow.json` (listed in `images/README.md`). The diagrams add no claim: every number in them was in the ASCII block they replace and is sourced in "Router: classifier" and "Router: data" above (8,000 characters, 384 dimensions, 4 outputs; 12 stacks, 4 shapes, 16 prompts per cell, 192 and 96 cells, 4,412, 2,406, 2,006, 1,003 confident, 1,003 unsure, 3,409, train 2,706, val 303, eval 400 with 100 per Tier). `article-en-medium.md` had no diagram and has none now.

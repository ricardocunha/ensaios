---
title: "Compliance agents that know when they're unsure"
subtitle: "Reviewing Brazilian public contracts with Docling, MCP and Pydantic AI, and measuring when the agent should hand the case to a human"
platforms: Medium, dev.to, Hashnode
status: DRAFT — replace every [[RESULT: …]] before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents
---

# Compliance agents that know when they're unsure

A compliance agent that is right 80% of the time is useless if you can't tell *which* 80%. A human then has to re-check everything, and the agent has saved nothing. The useful agent is the one that says *"I'm not sure about this one"* on the right cases.

This article builds one and measures it. The documents are real Brazilian public-procurement contracts from PNCP, the national procurement portal. The rules come from Lei 14.133/2021, the procurement law. The stack is the one from the video *"5 AI Agents Projects to Build in 2026"* (project #4): **Docling** to parse scanned PDFs, an **MCP server** to expose them, and **Pydantic AI** for the agents. Everything runs on a laptop with an open 8B model.

Every number below comes from the repo's `docs/RESULTS.md`. Every bug I hit is in there too, because most of what I learned came from them.

## The setup

```
PNCP contract PDF ─► Docling (+ Apple Vision OCR, pt-BR) ─► sections, page scores
                                     │
                         MCP server: parse_document · get_section · search_document · verify_quote
                                     │
          Reviewer (Pydantic AI, one run per rule) ─► Finding{verdict, quote, confidence}
                                     │
          Auditor (tries to refute violations) + deterministic checks ─► keep or escalate
```

- **Eight rules** from Lei 14.133, each tied to an article I checked against the official text: the object clause, binding to the tender notice (*vinculação*), price and payment, the price-adjustment index (art. 92 § 3º), the budget allocation, the jurisdiction (*foro*) clause (art. 92 § 1º), the guarantee limit (art. 98) and the contract-term limits (arts. 106–107).
- **Ground truth:** 60 synthetic contracts in the usual structure, with 0–2 **planted violations** each. They also include **hard compliant cases**: legal variants that look suspicious, such as an 8% guarantee *with* the justification art. 98 requires, a 60-month term, or a *foro* written as "Comarca de <seat>".
- **Model:** Qwen3-8B 4-bit on a local mlx-lm server. It costs nothing per document, which matters when every experiment is hundreds of agent runs.

## Part 1: how good is OCR on contracts, and does Docling know when it's wrong?

Real scans are rarer on PNCP than I expected. In my first sample, 6 of 8 PDFs with no text layer turned out to be **blank pages**, broken uploads. So I built a benchmark with known answers. I took 20 born-digital contracts from 10 public bodies, kept their text layer as ground truth, and rendered them as image-only "scans" at four degradation levels.

| Level | Word recall | Number recall | Docling `ocr_score` |
|---|---|---|---|
| clean (300 dpi) | 95.1% | 91.6% | 0.994 |
| mild (200 dpi) | 96.6% | 96.6% | 0.994 |
| medium (150 dpi) | 95.5% | 91.7% | 0.993 |
| heavy (110 dpi, skewed, faded) | 48.0% | 39.6% | 0.852 |

I track **number recall** separately because in a contract a wrong number (an amount, a percentage, a deadline) matters more than a wrong word.

**Can Docling's own confidence find the bad pages?** When `ocr_score` is below 0.95, the page really is bad 94% of the time. But that flag catches **only 34% of the bad pages**. The rest look fine to Docling. On clean pages, for example, the letterhead's small print had its postal code read as 46304-053 instead of 88304-053, with `ocr_score` = 1.0. So a low score is a signal worth using, but a high score doesn't mean the page is clean.

**Four of my first "OCR errors" were my own measurement bugs.** Each one showed up as a number that looked wrong:
1. Docling moves paragraph numbers ("5.3") out of the text into a `marker` field. They looked like OCR misses, and they were also missing from what the agent read, even though they're exactly what a finding needs to cite.
2. Headers and footers are Docling "furniture" and are left out of the body by default.
3. Some text layers split "14.3" across two lines, so the OCR's correct answer was scored as wrong.
4. The blank-page uploads mentioned above.

## Part 2: the reviewer, and why the tools mattered more than the prompt

The reviewer is a Pydantic AI agent with **one run per rule**. That's easier for an 8B model, and it gives each rule its own finding to escalate or keep. It reads the contract only through the MCP tools, and it must quote its evidence verbatim.

**Tool output beat prompt changes, twice.**

- ***Foro.*** On a Receita Federal contract ("É eleito o Foro de CURITIBA"), the reviewer said *violation* **3 times out of 3, at 0.95 confidence**. The contracting office is in Curitiba, so the clause is compliant. The agent never looked at the preamble, where the parties are named. Telling it to read the preamble changed nothing. Returning the preamble inside `parse_document`'s output fixed it: **3 of 3 correct**.
- ***Vinculação.*** In the first baseline this rule produced **10 false alarms in 20 contracts**. The agent searched for "vinculação", my search tool required exact words, and the contract said "vincula-se". The search returned nothing, and the agent concluded the clause was missing. The fix was matching on word stems.

**Let the model extract and code decide.** On the guarantee and term rules the 8B model quoted "12 (doze) meses" correctly and then said it exceeds "5 anos". Those two rules had 23 false alarms in 40 findings. Now the model only **extracts** values (percentage, justification quote, months, whether the service is continuous) and ten lines of Python apply the law. It's the same split as in my previous article: the model reads, rules decide.

Together, the two fixes took accuracy from **74.4% to 95.0%** and cut false alarms **from 34 to 6**. All 11 hard compliant cases are now right, against 4 before. Recall dipped slightly, from 22 to 21 of 23 violations found.

| Reviewer | Violations found (recall) | Precision | False alarms | Hard cases right | Quotes verbatim |
|---|---|---|---|---|---|
| Baseline (text PDFs) | 95.7% | 39.3% | 34 | 4/11 | 134/146 |
| + stem search, code-decided limits | 91.3% | **77.8%** | **6** | **11/11** | 150/153 |

## Part 3: when should the agent escalate?

The model's **self-reported confidence** carries almost no information. In the baseline, 88% of findings had confidence ≥ 0.95, and accuracy on those was 80.7% against 74.4% overall. Three runs of the same wrong answer also **agreed 3 out of 3**, so agreement alone can't catch a mistake the model makes every time.

So escalation uses signals the model can't talk its way around:

- **disagreement** across 3 samples;
- a **quote that isn't in the document** (checked in code);
- a **low OCR score** on the pages the evidence comes from;
- an **auditor** that tries to refute each violation with its own search, and whose objection counts only if it comes with a verbatim counter-quote.

[[RESULT: escalation table: policy × escalated % × accuracy on kept × errors caught, on text and on heavy scans]]

[[RESULT: the curve, accuracy on what is kept vs. share escalated]]

## Part 4: real contracts

[[RESULT: 20 real PNCP contracts, labeled by hand: agreement with the reviewer, what it gets wrong on real text]]

## What I'd tell a team building this

1. **Measure OCR on your own documents, with ground truth.** It was fine up to medium degradation and collapsed on heavy scans. Docling's confidence is a trustworthy flag when it's low, and says little when it's high.
2. **Fix tools before prompts.** Both of the reviewer's systematic errors were information problems: a missing preamble and a search that couldn't match a verb form. More instructions didn't fix either one.
3. **Don't let an 8B model do arithmetic on legal limits.** Have it extract the values and decide in code.
4. **Don't trust the model's confidence.** Build escalation from checks outside the model: disagreement, verbatim quotes, OCR quality, and an adversarial second agent.

---

*Idea from the video "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (project #4). Code, data pipeline and every number: [github.com/ricardocunha/ensaios › articles/2026-10-compliance-document-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents). The contracts are public; the repo doesn't redistribute them, and quotes here have names redacted. This is a test bench, not legal advice.*

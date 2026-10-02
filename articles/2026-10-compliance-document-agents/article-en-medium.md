---
title: "Compliance agents that know when they're unsure"
subtitle: "An open 8B model reviewing Brazilian public contracts, and the checks that decide when a human should look"
platforms: Medium (short version; the full version is article-en.md, for dev.to / Hashnode)
status: DRAFT — fill in the real-contracts result before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents
---

# Compliance agents that know when they're unsure

A compliance agent that is right 80% of the time is useless if you can't tell *which* 80%: someone has to re-check everything. The useful agent says *"I'm not sure about this one"* on the right cases.

I built one for Brazilian public-procurement contracts (from PNCP, the national portal), checking eight rules from the procurement law, Lei 14.133/2021. The stack comes from project #4 of the video *"5 AI Agents Projects to Build in 2026"*: **Docling** parses scanned PDFs, an **MCP server** exposes them, and **Pydantic AI** runs the agents. The model is **Qwen3-8B on a laptop**, at no cost per document.

To measure it, I generated 20 synthetic contracts with planted violations, plus legal-but-suspicious cases: an 8% guarantee *with* the justification the law requires, a term exactly at the 5-year limit.

## OCR: fine until it isn't, and Docling half-knows it

I rendered 20 real born-digital contracts as image-only "scans" at four degradation levels and compared Docling's OCR with the original text. Up to medium degradation it recovered 95–97% of the words and 92–97% of the numbers. On heavy scans it got 48% of the words and 40% of the numbers.

When Docling's `ocr_score` is below 0.95, the page really is bad 94% of the time, but that flag catches only a third of the bad pages. A postal code in small print was read wrong with a score of 1.0.

## The fixes that mattered were in the tools, not the prompt

- **The jurisdiction clause.** The reviewer called "Foro de CURITIBA" a violation 3 times out of 3, at 0.95 confidence. The contracting office *is* in Curitiba, but the agent never read the preamble. Telling it to read the preamble did nothing. Returning the preamble inside the tool's output fixed it.
- **A search that couldn't conjugate.** The agent searched for "vinculação", the contract said "vincula-se", and my search matched whole words only. It concluded the clause was missing, ten times. The fix was matching word stems.
- **Arithmetic.** The model quoted "12 (doze) meses" and then said it exceeds "5 anos". Now it only extracts the values, and a few lines of Python apply the legal limits.

Together these took accuracy from **74% to 95%** and false alarms **from 34 to 6**, and all the legal-but-suspicious cases became right.

## When to escalate: one signal is never enough

The model's own confidence was useless on clean text: almost everything came back ≥ 0.95. So I escalate on checks the model can't talk its way around: **3 samples that disagree**, a **quote that isn't in the document**, a **low OCR score**, and an **auditor agent** that tries to refute each reported violation.

| | Clean text | Heavy scans |
|---|---|---|
| Accuracy, no escalation | 97.5% | **47.5%** |
| Escalate when samples disagree | 11% escalated, 99.3% right on the rest | catches only 30% of errors |
| Escalate when OCR score < 0.9 | escalates nothing | catches 82% of errors |
| Any of the four checks | 18% escalated, 99.2% right | 93% escalated, 100% right on the rest |

On heavy scans the reviewer reports unreadable clauses as "missing", *every time*, so its samples agree and disagreement can't catch it. OCR quality can. On clean text it's the other way around. **Combine them.**

The auditor caught every false alarm on clean text, and also argued with a third of the real violations, using quotes that exist but don't support its point. A verbatim check proves a quote is real, not that it's relevant. A dispute escalates and never overturns, so the cost is review time.

## Real contracts

[[RESULT: 20 real PNCP contracts, labeled by hand: agreement with the reviewer]]

## What I'd tell a team

1. **Measure OCR on your own documents, with ground truth.** Treat a low score as a warning and a high score as no guarantee.
2. **Fix the tools before the prompt.** Both systematic errors were information problems.
3. **Never let a small model do arithmetic on legal limits.** It extracts, code decides.
4. **Build escalation from several outside checks.** Disagreement and OCR quality fail in opposite places.

---

**Code, data pipeline and every number:** [github.com/ricardocunha/ensaios › articles/2026-10-compliance-document-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents)

*The contracts are public; the repo doesn't redistribute them, and quotes have names redacted. A test bench, not legal advice. Idea: "5 AI Agents Projects to Build in 2026" (project #4).*

#AI #Agents #LLM #DocumentAI #OCR #Compliance #OpenSource #Brazil

# Plan: Compliance agents that know when they're unsure

**Branch:** `article/2026-10-compliance-document-agents` · **Target date:** 2026-10-30 · **Video project:** #4 (legal / compliance document agents)

## Question

Can a document-review agent over scanned contracts say *"I'm not sure, a human should look"* at the right moments, and how do we measure that?

## Brazilian angle

Public procurement contracts and bid notices (*editais*, *contratos administrativos*) published on public portals, checked against a small rule set inspired by Lei 14.133/2021 (for example: deadline clauses, guarantee limits, required annexes). Public documents, so no personal-data issue. [[VERIFY: portal source (PNCP API?) and terms of use]]

## Architecture

1. **Parse:** Docling on scanned PDFs → structured blocks (sections, tables). Exposed as an **MCP server** (`parse_document`, `get_section`), so any agent can use it.
2. **Review agent:** Pydantic AI with typed outputs (`Finding{rule, clause_ref, verdict, evidence, confidence}`).
3. **Uncertainty profiling:** confidence from agreement across N samples plus OCR quality signals (Docling confidence, low-quality pages). A below-threshold result goes to **escalation**.
4. **Auditor:** a second agent that checks every finding cites real text (evidence is a verbatim span; this check is deterministic).
5. Optional: the same agent in **Google ADK** for a short "framework comparison" section, only if time allows.

## Reuse from the CNH article

OCR noise injection (`noise.py`), "the vision model reads, rules decide" (ADR 0003), and the synthetic ground-truth idea: plant known violations in synthetic contracts.

## Evaluation

- Synthetic contracts with planted violations (ground truth) + ~20 real public contracts labeled by hand.
- Metrics: finding precision / recall; **selective accuracy** (accuracy on what the agent didn't escalate) vs. escalation rate; evidence hallucination rate (auditor).

## Milestones

1. Docling MCP server + parse quality on 20 scanned PDFs.
2. Pydantic AI reviewer on clean text.
3. Synthetic planted-violation generator + evaluation.
4. Uncertainty + escalation curve; auditor.
5. Drafts.

## Open questions

- A small rule set (5–8 rules) vs. a broad one: start small.
- Model: local Qwen3-8B (from the CNH article) vs. an API model for the reviewer.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.

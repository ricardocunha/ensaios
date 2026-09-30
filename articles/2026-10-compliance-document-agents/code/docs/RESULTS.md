# Results

## 1. OCR on degraded scans (`make ocr-eval`, 2026-09-30)

20 PNCP contracts with a text layer (at most 2 per public body, 10 bodies), first 6 pages, rendered at 4 degradation levels and read back by Docling 2.131 with Apple Vision OCR (pt-BR). Ground truth: the original text layer. Pages with < 200 characters excluded (82 pages per level).

| Level | Word recall | Number recall | CER* | Docling `ocr_score` (mean) |
|---|---|---|---|---|
| clean (300 dpi) | 95.1% | 91.6% | 0.133 | 0.994 |
| mild (200 dpi) | 96.6% | 96.6% | 0.144 | 0.994 |
| medium (150 dpi) | 95.5% | 91.7% | 0.199 | 0.993 |
| heavy (110 dpi, skew 3°, faded) | 48.0% | 39.6% | 0.445 | 0.852 |

<sub>*CER is order-sensitive: Docling orders headers, footers and tables differently from the text layer, so CER overstates errors. Word and number recall are order-insensitive.</sub>

**Does Docling's confidence find the bad pages?** A "bad" page is one with number recall < 0.9 (132 of 324 pages).

| Flag pages with `ocr_score` below | Pages flagged | Precision | Recall |
|---|---|---|---|
| 0.99 | 145 | 0.63 | 0.69 |
| 0.97 | 60 | 0.90 | 0.41 |
| 0.95 | 48 | 0.94 | 0.34 |
| 0.90 | 35 | 0.97 | 0.26 |

Spearman(`ocr_score`, CER) = −0.50 across all pages; within the heavy level, −0.65; within the others, −0.14 to −0.25.

Takeaways:
- Mild and medium degradation cost almost nothing; heavy degradation loses half the words and 60% of the numbers.
- A low `ocr_score` is trustworthy (≥ 0.90 precision below 0.97) but it misses most bad pages. It can't be the only escalation signal.
- On clean pages most number misses are page numbers (metric noise), but some are real: the letterhead's small print (postal code 88304-053 read as 46304-053; phone …6029 as …6023), with `ocr_score` = 1.0.

### Metric bugs found on the way (each was caught by checking a number that looked wrong)
1. Docling moves paragraph numbers ("5.3") into `marker`; they looked like OCR misses and, worse, were missing from what the reviewer read. Fixed in `parse.item_text`.
2. Headers and footers are Docling "furniture", excluded by default from `iterate_items`; now included for the comparison.
3. Some text layers split numbers across lines ("14.\r\n3"), so the OCR's correct "14.3" counted as wrong. Numbers are now joined before comparison.
4. Six of the first eight "scanned" PNCP PDFs were blank pages.

## 2. Reviewer smoke tests (Qwen3-8B 4-bit, local)

- `foro` rule on a Receita Federal contract ("É eleito o Foro de CURITIBA"; the contracting body sits in Curitiba): **violation, 3/3 samples, confidence 0.95**, before the fix. The reviewer never opened the preamble, despite an instruction to. With thinking on, still a violation (it keyed on a typo in the contract, "Lei nº 14.333/2021").
- After `parse_document` started returning the preamble: **compliant, 3/3**, citing Curitiba. Changing the tool's output fixed what changing the instructions didn't.
- Sample agreement was 3/3 on the wrong answer: agreement alone won't catch systematic mistakes.

## 3. Reviewer on 20 synthetic contracts (text PDFs, 8 rules, 1 sample, Qwen3-8B 4-bit local)

| | Baseline | v2: stem search + code-decided limits |
|---|---|---|
| Accuracy (160 findings) | 74.4% | **95.0%** |
| Violations found (recall) | 22/23 (95.7%) | 21/23 (91.3%) |
| Violation precision | 39.3% | **77.8%** |
| False alarms | 34 | **6** |
| Hard compliant cases right | 4/11 | **11/11** |
| Quotes verbatim | 134/146 | 150/153 |
| Unanswered (invalid output) | 7 | 1 |

Baseline false alarms by rule: vigencia_limite 13, garantia_limite 10, vinculacao 10, preco_pagamento 1. Causes: search matched whole words only ("vinculação" never found "vincula-se"); arithmetic on limits ("12 meses excede 5 anos"). v2 remaining false alarms: reajuste 3, vigencia_limite 2, objeto 1. Missed: foro 1, garantia_limite 1.

Self-reported confidence: baseline 88% of findings ≥ 0.95 with 80.7% accuracy on them (74.4% overall); v2 94% ≥ 0.95 with 95.3% (95.0% overall). It barely separates right from wrong.

Runs: `runs/review_text_baseline.jsonl`, `runs/review_text_v2.jsonl` (git-ignored; regenerate with `make review`).

## 4. Escalation on text PDFs (20 synthetic contracts × 8 rules × 3 samples, v2 reviewer, majority vote)

160 decisions. "Escalated" always includes decisions with no valid answer. 20 of 480 runs failed with a connection error to the local server (one burst); they will be re-run (`--redo-errors`), so this table is provisional.

| Escalate when | Escalated | Accuracy on kept | Errors caught | Violations missed and not escalated |
|---|---|---|---|---|
| never escalate | 4% | 97.4% | 60% | 1 |
| self-confidence < 0.9 | 11% | 97.2% | 60% | 1 |
| samples disagree | 16% | 99.3% | 90% | 1 |
| quote not verbatim | 6% | 97.3% | 60% | 1 |
| page quality < 0.9 | 4% | 97.4% | 60% | 1 |
| disagree OR not verbatim | 16% | 99.3% | 90% | 1 |
| disagree OR not verbatim OR quality < 0.9 | 16% | 99.3% | 90% | 1 |
| auditor disputes | 18% | 99.2% | 90% | 1 |
| all of the above | 22% | 99.2% | 90% | 1 |

- Majority vote of 3 samples alone: 97.4% accuracy on kept decisions (single sample, v2: 95.0%).
- **Escalating when samples disagree** sends 16% to a human, catches 90% of the wrong decisions, and leaves 99.3% accuracy on the rest.
- On clean text, OCR quality and quote verification add nothing beyond disagreement.

**Auditor** (tries to refute each reported violation; a dispute counts only with a verbatim counter-quote): 69 violation findings audited.

| | Auditor agrees | Auditor disputes |
|---|---|---|
| True violation | 36 | 20 |
| False alarm | 0 | **13** |

It disputed every false alarm, and also 36% of the true violations, with quotes that are real but irrelevant (e.g. quoting "72 (setenta e dois) meses" against a 72-month-term violation). The verbatim check proves a quote exists, not that it supports the claim. Because a dispute escalates and never overturns, nothing wrong is kept; the cost is human review time.

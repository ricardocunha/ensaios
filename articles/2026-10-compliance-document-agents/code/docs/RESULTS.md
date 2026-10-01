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

## 4. Escalation (20 synthetic contracts × 8 rules × 3 samples, v2 reviewer, majority vote; final, after re-running connection errors)

160 decisions per condition. "Escalated" always includes decisions with no valid answer. Remaining failures are model failures only (invalid output after 3 retries): 9/480 on text, 25/480 on heavy scans.

### Text PDFs

| Escalate when | Escalated | Accuracy on kept | Errors caught | Violations missed and not escalated |
|---|---|---|---|---|
| never escalate | 0% | 97.5% | 0% | 1 |
| self-confidence < 0.9 | 7% | 97.3% | 0% | 1 |
| samples disagree | 11% | 99.3% | 75% | 1 |
| quote not verbatim | 2% | 97.4% | 0% | 1 |
| page quality < 0.9 | 0% | 97.5% | 0% | 1 |
| disagree OR not verbatim | 12% | 99.3% | 75% | 1 |
| disagree OR not verbatim OR quality < 0.9 | 12% | 99.3% | 75% | 1 |
| auditor disputes | 13% | 99.3% | 75% | 1 |
| all of the above | 18% | 99.2% | 75% | 1 |

- Majority of 3 samples: 97.5% accuracy (single sample: 95.0%).
- **Samples disagree** escalates 11% and catches 75% of the wrong decisions; 99.3% accuracy on the rest.
- Self-confidence, quote verification and page quality add nothing on clean text.

### Heavy scans (110 dpi, 3° skew, faded)

| Escalate when | Escalated | Accuracy on kept | Errors caught | Violations missed and not escalated |
|---|---|---|---|---|
| never escalate | 0% | 47.5% | 0% | 4 |
| self-confidence < 0.9 | 77% | 73.0% | 88% | 1 |
| samples disagree | 33% | 44.9% | 30% | 3 |
| quote not verbatim | 8% | 49.0% | 11% | 4 |
| page quality < 0.9 | 77% | 59.5% | 82% | 0 |
| disagree OR not verbatim | 37% | 45.5% | 35% | 3 |
| disagree OR not verbatim OR quality < 0.9 | 87% | 61.9% | 90% | 0 |
| auditor disputes | 51% | 66.7% | 69% | 3 |
| all of the above | 93% | 100.0% | 100% | 0 |

- The reviewer collapses: 47.5% accuracy. Of 137 compliant checks it called 80 violations: it can't find the clause in garbled OCR and reports it missing, **consistently**, so the samples agree and disagreement catches only 30% of the errors.
- **OCR page quality** is the signal that works here (median page `ocr_score` 0.836): < 0.9 escalates 77% and catches 82% of errors. Self-confidence < 0.9 also works on scans (88% caught): the model does notice garbled text.
- All signals together escalate 93% and keep 100% accuracy on the remaining 7%: on a heavy scan, the right behaviour is to send almost everything to a human, and the signals do that.

**No single escalation signal works everywhere**: disagreement catches errors on clean text and misses them on bad scans; OCR quality is the opposite. Use both.

### Auditor

Tries to refute each reported violation (per sample); a dispute counts only with a verbatim counter-quote.

| | Text: agrees | Text: disputes | Heavy: agrees | Heavy: disputes |
|---|---|---|---|---|
| True violation | 40 | 19 | 31 | 19 |
| False alarm | 0 | **13** | 89 | **132** |

(Heavy: 8 more audits failed with invalid output.) On text it disputed every false alarm, and also a third of the true violations, with quotes that are real but irrelevant (e.g. quoting "72 (setenta e dois) meses" against a 72-month-term violation). The verbatim check proves a quote exists, not that it supports the claim. On heavy scans it disputed 60% of the false alarms. A dispute escalates and never overturns, so the cost is human review time, not wrong answers.

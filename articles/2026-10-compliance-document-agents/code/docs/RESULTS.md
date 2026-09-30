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

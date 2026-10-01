# Escalation uses checks outside the model, combined

A decision (one rule on one contract, majority of 3 samples) goes to a human if **any** of these holds: the samples disagree; the quoted evidence isn't verbatim in the document; the OCR score of the pages it comes from is below 0.9; the auditor disputes a reported violation with a verbatim counter-quote; or there is no valid answer.

Measured on 20 synthetic contracts × 8 rules (docs/RESULTS.md § 4): on text PDFs, disagreement alone escalates 11% and catches 75% of errors (99.3% accuracy on the rest); on heavy scans, disagreement catches only 30% (the model is consistently wrong: it reports unreadable clauses as missing) while OCR quality catches 82%. Combined, heavy scans are escalated almost entirely (93%), with 100% accuracy on what is kept.

## Considered options

- **Self-reported confidence**: no information on clean text (94% of findings ≥ 0.95); it does drop on garbled scans, so it is kept only as part of the combined rule, never alone.
- **Disagreement only**: misses systematic errors.
- **Letting the auditor overturn verdicts**: rejected; it disputed a third of the true violations with real but irrelevant quotes. A dispute escalates, never overturns.

## Consequences

Cost is human review time: 18% of decisions on text, 93% on heavy scans. A verbatim check proves a quote exists, not that it is relevant; that gap stays open.

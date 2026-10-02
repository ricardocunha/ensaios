# Glossary

- **Contract**: a public-procurement contract PDF from PNCP (*contrato administrativo*).
- **Section**: a block of a parsed contract that starts at a heading; in practice, usually a clause (*CLÁUSULA PRIMEIRA – DO OBJETO*).
- **Scan**: a PDF whose pages are images, with no usable text layer. A **degraded scan** is one we made from a text-layer PDF, so its true text is known.
- **Degradation level**: `clean` / `mild` / `medium` / `heavy` (resolution, skew, blur, noise, JPEG artifacts, faded ink).
- **Page quality** ("OCR score" in the articles): Docling's per-page `ocr_score`; escalation uses the lowest one on the pages a quote comes from. Docling also reports `layout_score`, `mean_score` and `low_score`, which are not used (layout confidence is low on perfectly readable pages).
- **Number recall**: the share of numeric tokens (amounts, dates, percentages, deadlines) on a page that OCR recovered exactly. In a contract, a wrong number is worse than a wrong word.
- **Finding**: the reviewer's verdict on one rule for one contract, with a quoted piece of evidence.
- **Escalation**: handing a decision to a human when any check outside the model fires: the samples disagree, the quote isn't verbatim, the OCR score of the quoted pages is below 0.9, the auditor disputes it, or there is no valid answer (ADR 0002). The model's self-reported confidence is not used.
- **Selective accuracy**: accuracy on the findings the agent did not escalate.

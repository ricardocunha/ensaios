# Glossary

- **Contract**: a public-procurement contract PDF from PNCP (*contrato administrativo*).
- **Section**: a block of a parsed contract that starts at a heading; in practice, usually a clause (*CLÁUSULA PRIMEIRA – DO OBJETO*).
- **Scan**: a PDF whose pages are images, with no usable text layer. A **degraded scan** is one we made from a text-layer PDF, so its true text is known.
- **Degradation level**: `clean` / `mild` / `medium` / `heavy` (resolution, skew, blur, noise, JPEG artifacts, faded ink).
- **Page quality**: Docling's per-page confidence (`ocr_score`, `layout_score`, `mean_score`, `low_score`).
- **Number recall**: the share of numeric tokens (amounts, dates, percentages, deadlines) on a page that OCR recovered exactly. In a contract, a wrong number is worse than a wrong word.
- **Finding**: the reviewer's verdict on one rule for one contract, with a quoted piece of evidence.
- **Escalation**: handing a finding to a human because the agent's confidence is below a threshold.
- **Selective accuracy**: accuracy on the findings the agent did not escalate.

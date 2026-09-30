# Data

| Source | What | License / terms | In git? |
|---|---|---|---|
| [PNCP](https://pncp.gov.br) public API (`/api/consulta/v1/contratos`, `/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}/arquivos`) | Contract PDFs from Brazilian public bodies, published under Lei 14.133/2021 | Public open data [[VERIFY: exact license statement of the PNCP / dados.gov.br open-data terms]] | **No** |
| Degraded scans (`compliance_agents.scans`) | The PNCP text-layer PDFs rasterized at 4 degradation levels; the original text layer is the ground truth | Derived from the above | **No** |
| `tests/fixtures/sample-contract.*` | A synthetic contract (fictitious parties) | Ours | Yes |

## Personal data

The contracts are public by law, but they name individual suppliers (sole proprietors whose company name is their own name) and signatories, sometimes with partially masked CPFs. So:

- PDFs, parses and scans stay in `data/` (git-ignored). The code downloads them; the repo never redistributes them.
- The article quotes only clause text with names, CPFs and CNPJs redacted, and identifies documents by PNCP control number at most.
- Planted-violation test documents are synthetic.

## Observations about PNCP

- In a sample of 18 PDFs with no text layer, **6 were blank pages** (broken or empty uploads). `pncp.py` checks the rendered pages for ink before counting a PDF as a scan.
- Real scans are rare. Most contracts are born-digital PDFs, so the OCR benchmark uses degraded renders of text-layer PDFs, plus the real scans that turned up as a sanity check.

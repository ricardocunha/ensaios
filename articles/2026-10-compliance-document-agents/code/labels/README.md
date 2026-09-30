# Hand labels for real contracts

`real_contracts.csv`: 20 PNCP contracts (16 public bodies, 10 real scans) × 8 rules = 160 rows.

For each row, open `data/pncp/<doc>.pdf` (run `make download` first) and fill in:

- `label`: `compliant`, `violation`, `not_applicable` or `unclear` (use `unclear` when the scan itself is unreadable).
- `section_or_quote`: the clause number, or a short quote (no names or CPFs).
- `notes`: anything surprising.

Before you label, the reviewer's proposal can be added in extra columns (`make propose-real`). Label blind if you can: fill `label` first, then compare.

Only identifiers are stored here (PNCP control numbers of public bodies); the contracts themselves are never committed.

"""Real-contract labels: list the sheet's documents, attach reviewer proposals, score against hand labels."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from compliance_agents.evaluate import flagged

SHEET = Path("labels/real_contracts.csv")


def docs(sheet: Path = SHEET) -> list[str]:
    with sheet.open() as f:
        return list(dict.fromkeys(r["doc"] for r in csv.DictReader(f)))


def propose(runs: Path, sheet: Path = SHEET, out: Path = Path("labels/real_contracts_proposed.csv")) -> None:
    found = {(r["doc"], r["rule"]): r for r in map(json.loads, runs.read_text().splitlines())}
    with sheet.open() as f, out.open("w", newline="") as g:
        reader = csv.DictReader(f)
        w = csv.DictWriter(g, fieldnames=[*reader.fieldnames, "reviewer_verdict", "reviewer_quote", "reviewer_reason"])
        w.writeheader()
        for row in reader:
            r = found.get((row["doc"], row["rule"]), {})
            w.writerow({**row, "reviewer_verdict": r.get("verdict", r.get("error", "")), "reviewer_quote": r.get("evidence", ""),
                        "reviewer_reason": r.get("reason", "")})
    print(f"wrote {out}")


def score(runs: Path, sheet: Path = SHEET) -> None:
    found = {(r["doc"], r["rule"]): r for r in map(json.loads, runs.read_text().splitlines())}
    n = agree = 0
    with sheet.open() as f:
        for row in csv.DictReader(f):
            if row["label"] not in ("compliant", "violation", "not_applicable"):
                continue
            n += 1
            agree += flagged(found.get((row["doc"], row["rule"]), {}).get("verdict")) == (row["label"] == "violation")
    print(f"{agree}/{n} findings agree with the hand labels" if n else "no hand labels yet")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["docs", "propose", "score"])
    ap.add_argument("--runs", type=Path, default=Path("runs/review_real.jsonl"))
    a = ap.parse_args()
    if a.cmd == "docs":
        print(" ".join(docs()))
    elif a.cmd == "propose":
        propose(a.runs)
    else:
        score(a.runs)


if __name__ == "__main__":
    main()

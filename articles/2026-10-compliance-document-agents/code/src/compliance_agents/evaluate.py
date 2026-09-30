"""Score reviewer runs against the synthetic labels.

Primary metric: did the reviewer flag the violations (binary: violation vs. not)? "compliant"
and "not_applicable" count as the same answer, since both mean "nothing to flag". Also:
evidence that isn't a verbatim quote (checked like the auditor does) and, per confidence
threshold, accuracy on what isn't escalated.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from compliance_agents import mcp_server
from compliance_agents.synth import HARD_COMPLIANT


def flagged(verdict: str | None) -> bool | None:
    """True = violation, False = nothing to flag, None = no usable answer (unclear / error)."""
    return {"violation": True, "compliant": False, "not_applicable": False}.get(verdict or "")


def evidence_ok(row: dict) -> bool | None:
    ev = (row.get("evidence") or "").strip()
    if not ev:
        return None
    return mcp_server.verify_quote(row["doc"], ev)["found"]


def score(rows: list[dict], labels: dict[str, dict]) -> dict:
    per_rule = defaultdict(lambda: {"n": 0, "correct": 0, "tp": 0, "fp": 0, "fn": 0, "unanswered": 0})
    hard = {"n": 0, "correct": 0}
    evidence = {"quoted": 0, "verbatim": 0}
    scored = []
    for r in rows:
        lab = labels[r["doc"]]
        truth = lab["labels"][r["rule"]] == "violation"
        pred = flagged(r.get("verdict"))
        s = per_rule[r["rule"]]
        s["n"] += 1
        if pred is None:
            s["unanswered"] += 1
            s["fn"] += truth
        else:
            s["correct"] += pred == truth
            s["tp"] += pred and truth
            s["fp"] += pred and not truth
            s["fn"] += truth and not pred
        rule_is_hard = any(HARD_COMPLIANT[h] == r["rule"] for h in lab["hard"])
        if rule_is_hard:
            hard["n"] += 1
            hard["correct"] += pred is not None and pred == truth
        ok = evidence_ok(r)
        if ok is not None:
            evidence["quoted"] += 1
            evidence["verbatim"] += ok
        scored.append({"confidence": r.get("confidence", 0.0), "correct": pred is not None and pred == truth})

    tot = {k: sum(s[k] for s in per_rule.values()) for k in ("n", "correct", "tp", "fp", "fn", "unanswered")}
    curve = []
    for th in (0.0, 0.5, 0.7, 0.8, 0.9, 0.95):
        kept = [x for x in scored if x["confidence"] >= th]
        curve.append({"threshold": th, "kept": len(kept) / max(1, len(scored)),
                      "accuracy": sum(x["correct"] for x in kept) / max(1, len(kept))})
    return {"per_rule": dict(per_rule), "total": tot, "hard": hard, "evidence": evidence, "confidence_curve": curve}


def report(res: dict) -> str:
    t = res["total"]
    prec = t["tp"] / max(1, t["tp"] + t["fp"])
    rec = t["tp"] / max(1, t["tp"] + t["fn"])
    lines = [
        f"Findings: {t['n']} · accuracy {t['correct'] / max(1, t['n']):.1%} · violations: precision {prec:.1%}, recall {rec:.1%} "
        f"({t['tp']} found, {t['fp']} false alarms, {t['fn']} missed) · unanswered {t['unanswered']}",
        f"Hard compliant cases: {res['hard']['correct']}/{res['hard']['n']} correct",
        f"Evidence: {res['evidence']['verbatim']}/{res['evidence']['quoted']} quotes verbatim",
        "",
        "| Rule | n | Accuracy | Found | False alarms | Missed |",
        "|---|---|---|---|---|---|",
    ]
    for rule, s in sorted(res["per_rule"].items()):
        lines.append(f"| {rule} | {s['n']} | {s['correct'] / max(1, s['n']):.0%} | {s['tp']} | {s['fp']} | {s['fn']} |")
    lines += ["", "| Keep findings with confidence ≥ | Kept | Accuracy on kept |", "|---|---|---|"]
    for c in res["confidence_curve"]:
        lines.append(f"| {c['threshold']} | {c['kept']:.0%} | {c['accuracy']:.1%} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path)
    ap.add_argument("--data", type=Path, default=Path("data/synth/text"))
    args = ap.parse_args()
    os.environ["COMPLIANCE_DATA_DIR"] = str(args.data)
    labels = {x["doc"]: x for x in map(json.loads, (args.data / "labels.jsonl").read_text().splitlines())}
    rows = [json.loads(line) for line in args.runs.read_text().splitlines()]
    print(report(score(rows, labels)))


if __name__ == "__main__":
    main()

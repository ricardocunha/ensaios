"""Uncertainty profile and escalation: when should a finding go to a human?

Groups the reviewer's samples per (contract, rule) into signals from outside the model
(agreement, verbatim evidence, page quality), then compares escalation policies: accuracy
on what the agent keeps vs. how much it escalates. See docs/adr/0002-escalation-signals.md.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from compliance_agents import mcp_server
from compliance_agents.evaluate import flagged


def decisions(rows: list[dict], audits: list[dict] | None = None) -> list[dict]:
    disputed = {(a["doc"], a["rule"]) for a in audits or [] if a.get("auditor_agrees") is False}
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["doc"], r["rule"])].append(r)
    out = []
    for (doc_id, rule), rs in groups.items():
        answers = [flagged(r.get("verdict")) for r in rs]
        counts = Counter(a for a in answers if a is not None)
        majority, votes = counts.most_common(1)[0] if counts else (None, 0)
        rep = next((r for r, a in zip(rs, answers) if a == majority), rs[0])
        doc = mcp_server._doc(doc_id)
        ev = (rep.get("evidence") or "").strip()
        verbatim = mcp_server.verify_quote(doc_id, ev)["found"] if ev else None
        sid = rep.get("section_id")
        pages = doc.sections[sid].pages if isinstance(sid, int) and 0 <= sid < len(doc.sections) else []
        quality = mcp_server._page_quality(doc, pages)
        out.append({
            "doc": doc_id, "rule": rule, "flag": majority, "samples": len(rs),
            "agreement": votes / len(rs), "verbatim": verbatim, "page_quality": quality,
            "self_confidence": sum(r.get("confidence", 0) for r in rs) / len(rs),
            "disputed": (doc_id, rule) in disputed,
        })
    return out


POLICIES = {
    "never escalate": lambda d: False,
    "self-confidence < 0.9": lambda d: d["self_confidence"] < 0.9,
    "samples disagree": lambda d: d["agreement"] < 1,
    "quote not verbatim": lambda d: d["verbatim"] is False,
    "page quality < 0.9": lambda d: (d["page_quality"] or 1) < 0.9,
    "disagree OR not verbatim": lambda d: d["agreement"] < 1 or d["verbatim"] is False,
    "disagree OR not verbatim OR quality < 0.9": lambda d: d["agreement"] < 1 or d["verbatim"] is False or (d["page_quality"] or 1) < 0.9,
    "auditor disputes": lambda d: d["disputed"],
    "all of the above": lambda d: d["agreement"] < 1 or d["verbatim"] is False or (d["page_quality"] or 1) < 0.9 or d["disputed"],
}


def compare(ds: list[dict], labels: dict[str, dict]) -> list[dict]:
    for d in ds:
        truth = labels[d["doc"]]["labels"][d["rule"]] == "violation"
        d["correct"] = d["flag"] is not None and d["flag"] == truth
        d["missed_violation"] = truth and d["flag"] is not True
    res = []
    for name, escalate in POLICIES.items():
        # an unanswered finding is always escalated
        esc = [d for d in ds if d["flag"] is None or escalate(d)]
        kept = [d for d in ds if not (d["flag"] is None or escalate(d))]
        wrong = [d for d in ds if not d["correct"]]
        res.append({
            "policy": name,
            "escalated": len(esc) / len(ds),
            "accuracy_kept": sum(d["correct"] for d in kept) / max(1, len(kept)),
            "errors_caught": sum(not d["correct"] for d in esc) / max(1, len(wrong)),
            "missed_violations_kept": sum(d["missed_violation"] for d in kept),
        })
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path)
    ap.add_argument("--data", type=Path, default=Path("data/synth/text"))
    ap.add_argument("--audit", type=Path, help="auditor results (jsonl)")
    args = ap.parse_args()
    os.environ["COMPLIANCE_DATA_DIR"] = str(args.data)
    labels = {x["doc"]: x for x in map(json.loads, (args.data / "labels.jsonl").read_text().splitlines())}
    audits = [json.loads(line) for line in args.audit.read_text().splitlines()] if args.audit else None
    ds = decisions([json.loads(line) for line in args.runs.read_text().splitlines()], audits)
    print(f"{len(ds)} decisions, {ds[0]['samples']} samples each\n")
    print("| Escalate when | Escalated | Accuracy on kept | Errors caught | Violations missed and not escalated |")
    print("|---|---|---|---|---|")
    for r in compare(ds, labels):
        print(f"| {r['policy']} | {r['escalated']:.0%} | {r['accuracy_kept']:.1%} | {r['errors_caught']:.0%} | {r['missed_violations_kept']} |")


if __name__ == "__main__":
    main()

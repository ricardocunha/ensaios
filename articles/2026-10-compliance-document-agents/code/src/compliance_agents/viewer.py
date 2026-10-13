"""Collect the run files into one JSON for the React viewer in `viewer/` (no model, no MCP process, no network).

    make viewer                                  # this, then the page at http://localhost:5176
    uv run python -m compliance_agents.viewer    # only viewer/public/data.json and the PDF link

Synthetic contracts only. Not legal advice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from compliance_agents import mcp_server
from compliance_agents.rules import RULES
from compliance_agents.uncertainty import POLICIES, compare, decisions

RUNS = Path("runs")
DATA = Path("data/synth")
OUT = Path("viewer/public")
# condition -> reviewer run files, first one present wins (`make review` writes the 1-sample v2 file)
CONDITIONS = {"text": ("review_text_x3.jsonl", "review_text_v2.jsonl"), "heavy": ("review_heavy_x3.jsonl",)}
ESCALATION = "all of the above"  # the rule of ADR 0002
SIGNALS = ("samples disagree", "quote not verbatim", "page quality < 0.9", "auditor disputes")
SAMPLE_KEYS = ("sample", "verdict", "section_id", "evidence", "confidence", "reason", "tool_calls", "tokens", "facts", "error", "redone")
ENV = "COMPLIANCE_DATA_DIR"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


@contextmanager
def _data_dir(path: Path):
    """Point the parser cache lookups of `mcp_server` at one condition's folder."""
    old = os.environ.get(ENV)
    os.environ[ENV] = str(path)
    try:
        yield
    finally:
        if old is None:
            del os.environ[ENV]
        else:
            os.environ[ENV] = old


def _parse(doc_id: str, level: str) -> dict:
    doc = mcp_server._doc(doc_id)
    return {
        "pages": doc.pages, "ocr_used": doc.ocr_used, "mean_grade": doc.mean_grade, "low_grade": doc.low_grade,
        "ocr_score_min": mcp_server._page_quality(doc, list(doc.page_scores)),
        "pdf": f"synth/{level}/{doc_id}.pdf",
        "sections": [asdict(s) for s in doc.sections],
    }


def _sample(row: dict, audit: dict | None) -> dict:
    out = {k: row[k] for k in SAMPLE_KEYS if k in row}
    evidence = (row.get("evidence") or "").strip()
    out["verbatim"] = mcp_server.verify_quote(row["doc"], evidence)["found"] if evidence else None
    if audit:
        out["audit"] = {k: audit[k] for k in ("auditor_agrees", "counter_quote", "counter_quote_verbatim", "auditor_reason", "error") if k in audit}
    return out


def _condition(level: str, runs: Path, data: Path) -> dict | None:
    """One condition's decisions, samples and parses, scored by `uncertainty` as `make` prints them."""
    run = next((runs / name for name in CONDITIONS[level] if (runs / name).exists()), None)
    if run is None:
        return None
    folder = data / level
    if not (folder / "labels.jsonl").exists():
        raise FileNotFoundError(f"no {folder}/labels.jsonl: run `make synth` first")
    labels = {x["doc"]: x for x in _rows(folder / "labels.jsonl")}
    rows = _rows(run)
    docs = sorted({r["doc"] for r in rows})
    missing = [d for d in docs if not (folder / f"{d}.parsed.json").exists()]
    if missing:  # the viewer never runs Docling
        raise FileNotFoundError(f"no parse cache for {missing[0]} in {folder}: run `uv run python -m compliance_agents.parse {folder}/*.pdf` first")
    audit_rows = _rows(runs / run.name.replace("review_", "audit_"))
    audits = {(a["doc"], a["rule"], a.get("sample", 0)): a for a in audit_rows}
    with _data_dir(folder):
        ds = decisions(rows, audit_rows)
        policies = compare(ds, labels)
        for d in ds:
            d["escalated"] = d["flag"] is None or POLICIES[ESCALATION](d)
            d["signals"] = {name: bool(POLICIES[name](d)) for name in SIGNALS}
        samples: dict[tuple[str, str], list[dict]] = {}
        for r in rows:
            samples.setdefault((r["doc"], r["rule"]), []).append(_sample(r, audits.get((r["doc"], r["rule"], r.get("sample", 0)))))
        parses = {d: _parse(d, level) for d in docs}
    by_policy = {p["policy"]: p for p in policies}
    summary = {
        "run": run.name, "decisions": len(ds), "samples": ds[0]["samples"] if ds else 0, "audited": bool(audit_rows),
        "accuracy": by_policy["never escalate"]["accuracy_kept"], "policies": policies,
        **{k: by_policy[ESCALATION][k] for k in ("escalated", "accuracy_kept", "errors_caught", "missed_violations_kept")},
    }
    items = {(d["doc"], d["rule"]): {"decision": {k: v for k, v in d.items() if k not in ("doc", "rule")}, "samples": samples[(d["doc"], d["rule"])]} for d in ds}
    return {"summary": summary, "items": items, "parses": parses, "labels": labels}


def build(runs: Path = RUNS, data: Path = DATA) -> dict:
    """One entry per (contract, rule) of the text run; the heavy-scan run is added when present."""
    found = {level: c for level in CONDITIONS if (c := _condition(level, runs, data))}
    if "text" not in found:
        raise FileNotFoundError(f"no {runs}/{CONDITIONS['text'][0]} or {runs}/{CONDITIONS['text'][1]}: run `make review` first (needs `make synth` and `make serve`)")
    labels = found["text"]["labels"]
    order = {r.id: i for i, r in enumerate(RULES)}
    items = []
    for doc, rule in sorted(found["text"]["items"], key=lambda k: (k[0], order.get(k[1], len(order)))):
        lab = labels[doc]
        items.append({
            "id": f"{doc}/{rule}", "doc": doc, "rule": rule, "label": lab["labels"][rule],
            "conditions": {level: c["items"][(doc, rule)] for level, c in found.items() if (doc, rule) in c["items"]},
        })
    contracts = {
        doc: {"planted": labels[doc].get("planted", []), "hard": labels[doc].get("hard", []),
              "parses": {level: c["parses"][doc] for level, c in found.items() if doc in c["parses"]}}
        for doc in sorted({i["doc"] for i in items})
    }
    return {
        "summary": {level: c["summary"] for level, c in found.items()},
        "rules": {r.id: {"article": r.article, "kind": r.kind, "check": r.check, "law": r.law} for r in RULES},
        "contracts": contracts,
        "items": items,
    }


def write(data: dict, out: Path = OUT, root: Path = DATA) -> Path:
    """Write data.json and link the synthetic PDFs next to it (both git-ignored; nothing is copied)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False))
    link = out / "synth"
    if link.is_symlink():
        link.unlink()
    if not link.exists():
        link.symlink_to(root.resolve(), target_is_directory=True)
    return out / "data.json"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=Path, default=RUNS)
    p.add_argument("--data", type=Path, default=DATA, help="the synthetic contracts (text/, heavy/)")
    p.add_argument("--out", type=Path, default=OUT)
    a = p.parse_args(argv)
    try:
        data = build(a.runs, a.data)
    except FileNotFoundError as e:
        sys.exit(str(e))
    path = write(data, a.out, a.data)
    print(f"{len(data['items'])} decisions ({', '.join(data['summary'])}) -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()

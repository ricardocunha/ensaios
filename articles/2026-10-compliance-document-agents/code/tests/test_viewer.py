import json

import pytest

from compliance_agents.rules import RULES
from compliance_agents.viewer import build, write


def _jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows))


def _review(rule, verdict, sample, evidence="", section_id=None):
    return {"doc": "synth-000", "rule": rule, "verdict": verdict, "section_id": section_id, "evidence": evidence,
            "confidence": 0.9, "reason": "r", "tool_calls": 1, "tokens": 10, "sample": sample, "decide": "code"}


def _fixture(tmp_path, ocr_score=None):
    runs, data = tmp_path / "runs", tmp_path / "synth"
    runs.mkdir()
    labels = {r.id: "compliant" for r in RULES} | {"foro": "violation"}
    for level, score in (("text", None), ("heavy", ocr_score)):
        folder = data / level
        folder.mkdir(parents=True)
        (folder / "synth-000.pdf").write_bytes(b"%PDF")
        _jsonl(folder / "labels.jsonl", [{"doc": "synth-000", "planted": ["missing_foro"], "hard": [], "labels": labels}])
        parsed = {"doc_id": "synth-000", "source": "x", "pages": 1, "seconds": 0.1, "ocr_used": score is not None, "mean_grade": "good",
                  "low_grade": "fair", "page_scores": {"1": {"ocr_score": score} if score else {}},
                  "sections": [{"id": 0, "heading": "CLÁUSULA PRIMEIRA - DO OBJETO", "text": "1.1 O objeto é a limpeza predial.", "pages": [1]}], "markdown": ""}
        (folder / "synth-000.parsed.json").write_text(json.dumps(parsed))
    quote = "o objeto é a limpeza predial"
    _jsonl(runs / "review_text_x3.jsonl", [
        *[_review("objeto", "compliant", i, quote, 0) for i in range(3)],
        _review("foro", "violation", 0), _review("foro", "compliant", 1, "foro de Marte", 0),
        {"doc": "synth-000", "rule": "foro", "error": "boom", "sample": 2, "decide": "code"},
    ])
    _jsonl(runs / "audit_text_x3.jsonl", [{"doc": "synth-000", "rule": "foro", "sample": 0, "auditor_agrees": True, "counter_quote": "", "counter_quote_verbatim": False, "auditor_reason": "a"}])
    return runs, data


def test_build_groups_samples_per_contract_and_rule(tmp_path):
    runs, data = _fixture(tmp_path)
    out = build(runs, data)
    assert [i["id"] for i in out["items"]] == ["synth-000/objeto", "synth-000/foro"]  # the order of RULES
    objeto, foro = (i["conditions"]["text"] for i in out["items"])
    assert objeto["decision"]["correct"] and not objeto["decision"]["escalated"]
    assert [s["verbatim"] for s in objeto["samples"]] == [True, True, True]
    assert foro["decision"]["escalated"] and foro["decision"]["signals"]["samples disagree"]
    assert foro["samples"][0]["audit"]["auditor_agrees"] is True and foro["samples"][1]["verbatim"] is False
    assert foro["samples"][2] == {"sample": 2, "error": "boom", "verbatim": None}
    assert out["items"][1]["label"] == "violation" and out["contracts"]["synth-000"]["planted"] == ["missing_foro"]
    assert out["contracts"]["synth-000"]["parses"]["text"]["pdf"] == "synth/text/synth-000.pdf"
    assert out["summary"]["text"]["escalated"] == 0.5 and set(out["summary"]) == {"text"}
    assert out["rules"]["foro"]["article"] == "Art. 92, § 1º"


def test_build_adds_the_heavy_scan_with_its_page_quality(tmp_path):
    runs, data = _fixture(tmp_path, ocr_score=0.5)
    _jsonl(runs / "review_heavy_x3.jsonl", [_review("objeto", "compliant", 0, "o objeto é a limpeza predial", 0)])
    out = build(runs, data)
    heavy = out["items"][0]["conditions"]["heavy"]
    assert heavy["decision"]["page_quality"] == 0.5 and heavy["decision"]["signals"]["page quality < 0.9"] and heavy["decision"]["escalated"]
    assert out["contracts"]["synth-000"]["parses"]["heavy"]["ocr_score_min"] == 0.5
    assert "heavy" not in out["items"][1]["conditions"] and not out["summary"]["heavy"]["audited"]


def test_missing_run_names_the_make_target_and_write_links_the_pdfs(tmp_path):
    runs, data = _fixture(tmp_path)
    out = tmp_path / "public"
    for _ in range(2):  # a second run replaces the link
        path = write(build(runs, data), out, data)
    assert len(json.loads(path.read_text())["items"]) == 2
    assert (out / "synth").is_symlink() and (out / "synth").resolve() == data.resolve()
    (runs / "review_text_x3.jsonl").unlink()
    with pytest.raises(FileNotFoundError, match="make review"):
        build(runs, data)

from pathlib import Path

from compliance_agents.uncertainty import compare, decisions

FIX = Path(__file__).parent / "fixtures"


def test_policies(monkeypatch):
    monkeypatch.setenv("COMPLIANCE_DATA_DIR", str(FIX))
    rows = [
        # samples disagree on vigencia
        {"doc": "sample-contract", "rule": "vigencia_limite", "verdict": "violation", "evidence": "", "confidence": 0.9},
        {"doc": "sample-contract", "rule": "vigencia_limite", "verdict": "compliant", "evidence": "", "confidence": 0.9},
        {"doc": "sample-contract", "rule": "vigencia_limite", "verdict": "violation", "evidence": "", "confidence": 0.9},
        # invented quote on foro
        {"doc": "sample-contract", "rule": "foro", "verdict": "compliant", "evidence": "Fica eleito o foro de Marte", "confidence": 1},
    ]
    audits = [{"doc": "sample-contract", "rule": "vigencia_limite", "auditor_agrees": False}]
    ds = {d["rule"]: d for d in decisions(rows, audits)}
    assert ds["vigencia_limite"]["agreement"] == 2 / 3 and ds["vigencia_limite"]["flag"] is True
    assert ds["vigencia_limite"]["disputed"] is True
    assert ds["foro"]["verbatim"] is False
    labels = {"sample-contract": {"labels": {"vigencia_limite": "compliant", "foro": "compliant"}}}
    res = {r["policy"]: r for r in compare(list(ds.values()), labels)}
    assert res["never escalate"]["escalated"] == 0
    assert res["all of the above"]["escalated"] == 1.0
    assert res["samples disagree"]["errors_caught"] == 1.0  # the only wrong decision is vigencia

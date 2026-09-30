import json

import pytest

from disaster_risk.sources import cemaden, s2id, ufrgs_impact
from disaster_risk.sources._http import BlockedError, fetch, looks_like_waf_rejection

WAF_PAGE = (
    b"<html><head><title>Request Rejected</title></head><body>The requested URL was rejected. "
    b"Please consult with your administrator.<br><br>Your support ID is: 1</body></html>"
)


def test_waf_detection():
    assert looks_like_waf_rejection(WAF_PAGE)
    assert not looks_like_waf_rejection(b"ano;mes;uf\n2024;5;RS\n")


def test_fetch_reuses_cache(tmp_path):
    dest = tmp_path / "x.csv"
    dest.write_text("cached")
    assert fetch("http://example.invalid/x.csv", dest).read_text() == "cached"


def test_ufrgs_parse(fixtures):
    rows = ufrgs_impact.parse_csv((fixtures / "ufrgs_municipios.csv").read_text(encoding="utf-8"))
    assert [r.name for r in rows] == ["Canoas", "Porto Alegre", "São Leopoldo"]
    assert rows[0].ibge_code == "4304606"
    assert rows[0].people_affected == 154002
    assert rows[0].area_affected_pct == 48.6


def test_cemaden_snapshot_parse():
    raw = "﻿" + json.dumps(
        [{"idestacao": 7372, "uf": "RS", "codibge": 4317202, "cidade": "SANTA ROSA", "nomeestacao": "Glória",
          "ultimovalor": 0, "datahoraUltimovalor": "30/09/26 19:00", "acc24hr": "-"},
         {"idestacao": 1, "uf": "RS", "codibge": 4311809, "cidade": "MARAU", "nomeestacao": "x",
          "ultimovalor": 0, "datahoraUltimovalor": "30/09/26 19:00", "acc24hr": 12.4}]
    )
    rows = cemaden.parse_snapshot(raw.encode("utf-8"))
    assert rows[0].acc24h_mm is None and rows[1].acc24h_mm == 12.4


def test_cemaden_manual_file_missing_explains(tmp_path):
    with pytest.raises(FileNotFoundError, match="CAPTCHA"):
        cemaden.require_manual("RS", 2024, 5, data_dir=tmp_path)


def test_s2id_package_parse():
    pkg = {"result": {"resources": [
        {"name": "COBRADE", "format": "PDF", "url": "https://x/download/cobrade.pdf"},
        {"name": "1991 a 2025 - Danos Informados - Histórico de Desastres no Brasil", "format": "CSV",
         "url": "https://x/download/bd_atlas_1991_2025.csv", "last_modified": "2026-08-19"},
    ]}}
    res = s2id.history_resource(s2id.parse_package(pkg))
    assert res.filename == "bd_atlas_1991_2025.csv"


def test_blocked_error_is_runtime_error():
    assert issubclass(BlockedError, RuntimeError)

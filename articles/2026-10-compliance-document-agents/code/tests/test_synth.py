"""The labels must match what is actually printed in each synthetic contract."""

import random

import pypdfium2 as pdfium
import pytest

from compliance_agents.mcp_server import normalize
from compliance_agents.synth import VIOLATIONS, make_spec, render


@pytest.fixture(scope="module")
def contracts(tmp_path_factory):
    out = tmp_path_factory.mktemp("synth")
    rng = random.Random(3)
    specs = [make_spec(i, rng) for i in range(40)]
    texts = {}
    for s in specs:
        doc = pdfium.PdfDocument(render(s, out, seed=3))
        texts[s.doc_id] = normalize(" ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))))
        doc.close()
    return specs, texts


def test_planted_violations_break_their_rule(contracts):
    specs, _ = contracts
    for s in specs:
        for v in s.planted:
            rule, verdict = VIOLATIONS[v]
            assert s.labels()[rule] == verdict
        assert s.labels()["objeto"] == "compliant"


def test_text_matches_labels(contracts):
    specs, texts = contracts
    for s in specs:
        t, labels = texts[s.doc_id], s.labels()
        assert ("do foro" in t) == ("missing_foro" not in s.planted)
        assert ("dotacao orcamentaria" in t) == (labels["dotacao"] == "compliant")
        assert ("vincula-se ao edital" in t) == (labels["vinculacao"] == "compliant")
        assert ("data-base" in t) == (labels["reajuste"] == "compliant")
        if labels["garantia_limite"] == "not_applicable":
            assert "prestara garantia" not in t
        if "garantia_8_justificada" in s.hard:
            assert "garantia de 8%" in t and "complexidade tecnica" in t and labels["garantia_limite"] == "compliant"
        if "foro_outra_cidade" in s.planted:
            assert normalize(f"cidade de {s.seat[0]}/{s.seat[1]}, sede") not in t


def test_every_page_is_marked_synthetic(contracts):
    specs, texts = contracts
    assert all("documento sintetico" in texts[s.doc_id] for s in specs)

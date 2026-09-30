from docling_core.types.doc import DocItemLabel as L

from compliance_agents.mcp_server import normalize
from compliance_agents.parse import split_sections


def test_clause_lines_start_sections_even_when_docling_labels_them_text():
    s = split_sections([
        (L.TEXT, "Preâmbulo", 1),
        (L.TEXT, "CLÁUSULA PRIMEIRA - DO OBJETO", 1),
        (L.TEXT, "Objeto.", 1),
        (L.SECTION_HEADER, "CLAUSULA 2ª - DO PRAZO", 2),
        (L.TEXT, "Prazo.", 3),
    ])
    assert [x.heading for x in s] == ["(preâmbulo)", "CLÁUSULA PRIMEIRA - DO OBJETO", "CLAUSULA 2ª - DO PRAZO"]
    assert [x.id for x in s] == [0, 1, 2]
    assert s[2].pages == [2, 3]


def test_empty_preamble_is_dropped():
    s = split_sections([(L.SECTION_HEADER, "CLÁUSULA PRIMEIRA", 1), (L.TEXT, "x", 1)])
    assert len(s) == 1 and s[0].id == 0


def test_normalize_ignores_case_accents_and_spacing():
    assert normalize("Prazo de  VIGÊNCIA\n12") == normalize("prazo de vigencia 12")

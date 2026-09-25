"""BID ground-truth parsing: both annotation formats, value-before-label order, boilerplate."""

from cnh_ocr.evaluation.bid import read_regions, to_transcription
from cnh_ocr.evaluation.metrics import score_transcription

# Box format, 180°-rotated card; VALIDADE's value is listed before its label (as in BID 00003604).
BOX = """x, y, width, height, transcription
135, 173, 196, 10, FAVA STEFANELI KAWAHARA
140, 330, 40, 10, NOME
53, 103, 49, 16, CAT. HAB.
84, 91, 8, 9, C
113, 52, 86, 15, 1ª HABILITAÇÃO
90, 37, 97, 19, 27/04/1974
243, 37, 98, 17, 02/05/1993
293, 54, 54, 13, VALIDADE
492, 54, 71, 17, Nº REGISTRO
417, 39, 118, 13, 24554500997
599, 18, 18, 140, 404242510
644, 59, 15, 135, VÁLIDA EM TODO
"""

# Rotated-quad format.
POLY = """x, y, width, height, transcription
[10, 10, 60, 60], [10, 20, 20, 10], -1, -1, CPF
[10, 10, 90, 90], [25, 35, 35, 25], -1, -1, 896.630.040-53
[300, 300, 380, 380], [10, 20, 20, 10], -1, -1, LOCAL
[300, 300, 400, 400], [25, 35, 35, 25], -1, -1, CLÁUDIO-MG
[500, 500, 560, 560], [10, 20, 20, 10], -1, -1, ASSINATURA DO PORTADOR
"""


def _write(tmp_path, text):
    path = tmp_path / "x_gt_ocr.txt"
    path.write_bytes(text.encode("latin-1"))
    return path


def test_box_format_pairs_by_type_and_distance_not_file_order(tmp_path):
    t = to_transcription(read_regions(_write(tmp_path, BOX)))
    assert "VALIDADE: 02/05/1993" in t
    assert "1ª HABILITAÇÃO: 27/04/1974" in t
    assert "Nº REGISTRO: 24554500997" in t  # not the 9-digit espelho number
    assert "CAT. HAB.: C" in t
    assert "NOME: FAVA STEFANELI KAWAHARA" in t


def test_polygon_format_and_boilerplate_is_ignored(tmp_path):
    t = to_transcription(read_regions(_write(tmp_path, POLY)))
    assert t.splitlines() == ["CPF: 896.630.040-53", "LOCAL: CLÁUDIO-MG"]


def test_only_labels_present_in_truth_are_scored():
    truth = "CPF: 896.630.040-53\nLOCAL: CLÁUDIO-MG"
    pred = "NOME: SOMEONE\nCPF: 896.630.040-53\nLOCAL: CLAUDIO-MG"
    s = score_transcription(pred, truth)
    assert set(s["labels"]) == {"CPF", "LOCAL"}
    assert s["label_accuracy"] == 0.5

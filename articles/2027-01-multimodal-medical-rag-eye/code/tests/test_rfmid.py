import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import make_csv
from eye_rag.labels import CODES, DISEASE_RISK, NORMAL
from eye_rag.rfmid import downsize, label_matrix, parse_labels_csv, sha256


def test_parse_labels_csv_reads_labels_and_ids():
    text = make_csv([(1, {"DR"}), (2, set()), (3, {"MH", "ODC"})])
    recs = parse_labels_csv(text, "test", Path("img"))
    assert [r.id for r in recs] == ["test/1", "test/2", "test/3"]
    assert recs[0].labels == {"DR"} and recs[0].disease_risk == 1
    assert recs[1].labels == frozenset() and recs[1].label_set == {NORMAL}
    assert recs[2].labels == {"MH", "ODC"}
    assert recs[2].path == Path("img/3.jpg")


def test_parse_labels_csv_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing columns"):
        parse_labels_csv("ID,Disease_Risk,DR\n1,1,1\n", "train", Path("x"))


def test_label_matrix_with_disease_risk_column():
    recs = parse_labels_csv(make_csv([(1, {"DR"}), (2, set())]), "val", Path("x"))
    y = label_matrix(recs, (DISEASE_RISK, "DR", "MH"))
    assert y.tolist() == [[1, 1, 0], [0, 0, 0]]
    assert label_matrix(recs).shape == (2, len(CODES))


def test_downsize_caps_long_side_and_returns_rgb_jpeg():
    im = Image.fromarray(np.random.default_rng(0).integers(0, 255, (300, 500, 3), dtype=np.uint8))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    out = Image.open(io.BytesIO(downsize(buf.getvalue(), long_side=100)))
    assert out.format == "JPEG" and out.mode == "RGB" and out.size == (100, 60)


def test_downsize_does_not_upscale():
    buf = io.BytesIO()
    Image.new("RGBA", (40, 20)).save(buf, format="PNG")
    assert Image.open(io.BytesIO(downsize(buf.getvalue(), long_side=100))).size == (40, 20)


def test_sha256_matches_known_value():
    assert sha256(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

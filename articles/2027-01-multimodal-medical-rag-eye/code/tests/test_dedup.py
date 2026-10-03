import json

import numpy as np
from PIL import Image, ImageDraw

from eye_rag.dedup import (
    Pair,
    exclusions_from_pairs,
    fundus_crop,
    hamming_matrix,
    keep_mask,
    load_exclusions,
    match_inliers,
    phash,
    retina_features,
)


def fake_fundus(seed: int, shift=(0, 0), size=600) -> Image.Image:
    """A synthetic 'fundus': orange disc on black with random dark 'vessels' (lines)."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGB", (size + 100, size), "black")
    d = ImageDraw.Draw(im)
    cx, cy, r = size // 2 + 50, size // 2, size // 2 - 10
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(200, 110, 60))
    for _ in range(40):
        x0, y0 = rng.integers(cx - r // 2, cx + r // 2, 2)
        x1, y1 = x0 + rng.integers(-150, 150), y0 + rng.integers(-150, 150)
        d.line((x0 + shift[0], y0 + shift[1], x1 + shift[0], y1 + shift[1]), fill=(120, 40, 30), width=int(rng.integers(2, 6)))
    for _ in range(25):
        x, y = rng.integers(cx - r // 2, cx + r // 2, 2)
        d.ellipse((x + shift[0] - 6, y + shift[1] - 6, x + shift[0] + 6, y + shift[1] + 6), fill=(240, 220, 120))
    return im


def test_fundus_crop_removes_black_surround():
    im = fake_fundus(0)
    c = fundus_crop(im)
    assert im.size[0] == 700 and 575 <= c.size[0] <= 600  # disc diameter 580 (+ vessel overhang)


def test_phash_identical_zero_and_hamming_matrix():
    a, b = phash(fake_fundus(0)), phash(fake_fundus(1))
    assert a == phash(fake_fundus(0))
    h = hamming_matrix([a, b, 0], [a, b, 2**64 - 1])
    assert h[0, 0] == 0 and h[1, 1] == 0 and h[2, 2] == 64
    assert h[0, 1] == h[1, 0] > 0


def test_geometric_match_same_eye_vs_other_eye():
    same = match_inliers(retina_features(fake_fundus(3)), retina_features(fake_fundus(3, shift=(6, -4))))
    other = match_inliers(retina_features(fake_fundus(3)), retina_features(fake_fundus(4)))
    assert same >= 15
    assert other < 15


def _p(a, b, la=("DR",), lb=("DR",)):
    return Pair(a, b, 50, 0.99, 3, la, lb)


def test_exclusions_take_the_later_split_and_ignore_within_split():
    pairs = [_p("train/1", "test/5"), _p("test/7", "val/2", lb=("NORMAL",)), _p("train/3", "train/4"), _p("test/8", "test/9")]
    ex = exclusions_from_pairs(pairs)
    assert ex == {"val": [], "test": ["test/5", "test/7"]}
    assert not pairs[1].same_labels and pairs[1].cross_split and not pairs[2].cross_split


def test_load_exclusions_and_keep_mask(tmp_path):
    p = tmp_path / "ex.json"
    p.write_text(json.dumps({"exclude": {"val": ["val/1"], "test": ["test/2"]}}))
    ex = load_exclusions(p)
    assert keep_mask(["test/1", "test/2"], ex["test"]).tolist() == [True, False]

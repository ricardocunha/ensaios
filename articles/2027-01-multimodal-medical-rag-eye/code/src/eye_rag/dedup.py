"""Near-duplicate / same-eye audit across the RFMiD splits.

Two images show the same eye when a geometric match of the retina (SIFT + RANSAC)
has >= `INLIER_THRESHOLD` inliers, checked over **all** pairs; embedding cosine and
pHash are only reported next to it (see docs/DATA.md, "Duplicate audit"). The output
excludes each val/test image with a same-eye match in an earlier split; the official
split is unchanged.

    uv run python -m eye_rag.dedup     # writes docs/exclusions.json + runs/dedup_pairs.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.fft import dctn

BORDER_LEVEL = 20  # 0-255 grey level; fundus photos have a near-black surround
HASH_SIZE = 8  # 8 x 8 = 64-bit hash
HASH_SCALE = 4  # DCT over a 32 x 32 thumbnail

FEATURE_SIDE = 512  # long side of the image the keypoints are found on
INNER_DISC = 0.85  # keep keypoints inside this fraction of the fundus radius (no rim, no notch)
RATIO = 0.75  # Lowe ratio test
RANSAC_PX = 5.0
SCALE_RANGE = (0.8, 1.25)
MAX_ROTATION = 30.0  # degrees

# Set by inspecting pairs (docs/DATA.md, "Duplicate audit").
INLIER_THRESHOLD = 8  # exclusion: the noise floor of random pairs ends at ~6-7
HIGH_CONFIDENCE = 15  # reported separately: by eye, mostly the same eye

EXCLUSIONS = Path("docs/exclusions.json")
SPLIT_ORDER = ("train", "val", "test")


# --------------------------------------------------------------------------- signals


def fundus_crop(im: Image.Image, level: int = BORDER_LEVEL) -> Image.Image:
    """Crop to the bounding box of pixels brighter than `level` (the fundus disc)."""
    g = np.asarray(im.convert("L"))
    rows = np.flatnonzero((g > level).any(axis=1))
    cols = np.flatnonzero((g > level).any(axis=0))
    if len(rows) == 0 or len(cols) == 0:
        return im
    return im.crop((int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1))


def phash(im: Image.Image, hash_size: int = HASH_SIZE, scale: int = HASH_SCALE) -> int:
    """64-bit perceptual hash of the fundus: low-frequency DCT block vs its median
    (the classic pHash, as in `imagehash.phash`)."""
    n = hash_size * scale
    g = np.asarray(fundus_crop(im).convert("L").resize((n, n), Image.Resampling.LANCZOS), dtype=np.float64)
    d = dctn(g, norm="ortho")[:hash_size, :hash_size].flatten()
    bits = d > np.median(d)
    return int(sum(1 << i for i, b in enumerate(bits) if b))


def hamming_matrix(a: Sequence[int], b: Sequence[int]) -> np.ndarray:
    """(len(a), len(b)) Hamming distances between 64-bit hashes."""
    x = np.array(a, dtype=np.uint64)[:, None] ^ np.array(b, dtype=np.uint64)[None, :]
    out = np.zeros(x.shape, dtype=np.int16)
    for _ in range(64):
        out += (x & np.uint64(1)).astype(np.int16)
        x >>= np.uint64(1)
    return out


def retina_features(im: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """SIFT keypoint positions (n, 2) and descriptors (n, 128) of the retina."""
    import cv2

    im = fundus_crop(im).convert("RGB")
    im.thumbnail((FEATURE_SIDE, FEATURE_SIDE))
    g = np.ascontiguousarray(np.asarray(im)[:, :, 1])
    g = cv2.createCLAHE(2.0, (8, 8)).apply(cv2.GaussianBlur(g, (0, 0), 1.5))
    h, w = g.shape
    yy, xx = np.mgrid[:h, :w]
    mask = ((((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2) < INNER_DISC**2).astype(np.uint8) * 255
    kp, desc = cv2.SIFT_create().detectAndCompute(g, mask)
    if desc is None:
        return np.zeros((0, 2), np.float32), np.zeros((0, 128), np.float32)
    return np.array([k.pt for k in kp], np.float32), desc.astype(np.float32)


def match_inliers(a: tuple[np.ndarray, np.ndarray], b: tuple[np.ndarray, np.ndarray], matcher=None) -> int:
    """RANSAC inliers of a similarity transform a -> b, or 0 if the transform isn't a
    plausible re-photograph (scale, rotation) or there are too few matches."""
    import cv2

    (pa, da), (pb, db) = a, b
    if len(da) < 6 or len(db) < 6:
        return 0
    matcher = matcher or cv2.BFMatcher(cv2.NORM_L2)
    best: dict[int, cv2.DMatch] = {}
    for pair in matcher.knnMatch(da, db, k=2):
        if len(pair) == 2 and pair[0].distance < RATIO * pair[1].distance:
            m = pair[0]
            if m.trainIdx not in best or m.distance < best[m.trainIdx].distance:
                best[m.trainIdx] = m  # one-to-one: many-to-one matches fake inliers
    if len(best) < 6:
        return 0
    good = list(best.values())
    src = pa[[m.queryIdx for m in good]]
    dst = pb[[m.trainIdx for m in good]]
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX)
    if M is None:
        return 0
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    rot = abs(float(np.degrees(np.arctan2(M[1, 0], M[0, 0]))))
    if not (SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]) or rot > MAX_ROTATION:
        return 0
    return int(inl.sum())


# --------------------------------------------------------------------------- pairs -> exclusions


@dataclass(frozen=True)
class Pair:
    a: str  # record id, e.g. "train/1877"
    b: str
    inliers: int
    cosine: float
    hamming: int
    labels_a: tuple[str, ...]
    labels_b: tuple[str, ...]

    @property
    def same_labels(self) -> bool:
        return self.labels_a == self.labels_b

    @property
    def cross_split(self) -> bool:
        return self.a.split("/")[0] != self.b.split("/")[0]


def exclusions_from_pairs(pairs: Sequence[Pair], split_order: Sequence[str] = SPLIT_ORDER) -> dict[str, list[str]]:
    """For each pair across two splits, exclude the image from the *later* split
    (val is later than train, test later than both). Within-split pairs exclude nothing."""
    rank = {s: i for i, s in enumerate(split_order)}
    out: dict[str, set[str]] = {s: set() for s in split_order[1:]}
    for p in pairs:
        sa, sb = p.a.split("/")[0], p.b.split("/")[0]
        if sa == sb:
            continue
        later = p.a if rank[sa] > rank[sb] else p.b
        out[later.split("/")[0]].add(later)
    return {s: sorted(v, key=lambda x: int(x.split("/")[1])) for s, v in out.items()}


def load_exclusions(path: Path = EXCLUSIONS) -> dict[str, frozenset[str]]:
    """{split: ids to exclude} from the committed exclusion list."""
    d = json.loads(Path(path).read_text())
    return {s: frozenset(v) for s, v in d["exclude"].items()}


def keep_mask(ids: Sequence[str], excluded: frozenset[str]) -> np.ndarray:
    return np.array([i not in excluded for i in ids], dtype=bool)


# --------------------------------------------------------------------------- CLI


def compute_hashes(records: Sequence, cache: Path = Path("data/embeddings/phash.json")) -> list[int]:
    """pHash per record, cached by id."""
    store = json.loads(cache.read_text()) if cache.exists() else {}
    miss = [r for r in records if r.id not in store]
    for r in miss:
        with Image.open(r.path) as im:
            store[r.id] = phash(im)
    if miss:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(store))
    return [int(store[r.id]) for r in records]


def all_pair_inliers(feats: Sequence[tuple[np.ndarray, np.ndarray]], log_every: int = 200) -> np.ndarray:
    """(n, n) upper-triangular matrix of inliers for every pair (i < j)."""
    import cv2

    n = len(feats)
    out = np.zeros((n, n), dtype=np.int16)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    t = time.perf_counter()
    for i in range(n):
        for j in range(i + 1, n):
            out[i, j] = match_inliers(feats[i], feats[j], matcher)
        if log_every and (i + 1) % log_every == 0:
            print(f"  {i + 1}/{n} rows, {time.perf_counter() - t:.0f}s", file=sys.stderr)
    return out


def run(out_dir: Path = Path("runs"), exclusions_path: Path = EXCLUSIONS, cache: Path = Path("data/embeddings")) -> dict:
    from eye_rag.embed import image_embeddings

    t0 = time.perf_counter()
    data = {s: image_embeddings(s) for s in SPLIT_ORDER}
    recs = [r for s in SPLIT_ORDER for r in data[s][0]]
    vec = np.concatenate([data[s][1] for s in SPLIT_ORDER])
    ids = [r.id for r in recs]
    hashes = compute_hashes(recs, cache / "phash.json")

    inl_path = cache / "pair_inliers.npz"
    if inl_path.exists() and list(np.load(inl_path)["ids"]) == ids:
        inl = np.load(inl_path)["inliers"]
        t_feat = t_match = 0.0
    else:
        t = time.perf_counter()
        feats = []
        for r in recs:
            with Image.open(r.path) as im:
                feats.append(retina_features(im))
        t_feat = time.perf_counter() - t
        t = time.perf_counter()
        inl = all_pair_inliers(feats)
        t_match = time.perf_counter() - t
        np.savez_compressed(inl_path, ids=np.array(ids), inliers=inl)

    cos = vec @ vec.T
    ham = hamming_matrix(hashes, hashes)
    iu = np.triu_indices(len(ids), 1)
    c, h, k = cos[iu], ham[iu], inl[iu]
    split = np.array([i.split("/")[0] for i in ids])
    cross = split[iu[0]] != split[iu[1]]

    pairs = [
        Pair(ids[i], ids[j], int(inl[i, j]), round(float(cos[i, j]), 4), int(ham[i, j]),
             tuple(sorted(recs[i].label_set)), tuple(sorted(recs[j].label_set)))
        for i, j in zip(*np.nonzero(np.triu(inl >= INLIER_THRESHOLD, 1)), strict=True)
    ]
    excl = exclusions_from_pairs(pairs)

    def group(ps: list[Pair]) -> dict:
        return {"pairs": len(ps), "label_disagreement": sum(not p.same_labels for p in ps)}

    by_split: dict[str, dict] = {}
    for x, a in enumerate(SPLIT_ORDER):
        for b in SPLIT_ORDER[x:]:
            sel = [p for p in pairs if {p.a.split("/")[0], p.b.split("/")[0]} == {a, b}]
            by_split[f"{a}-{b}"] = {**group(sel), f"pairs_inliers>={HIGH_CONFIDENCE}": group([p for p in sel if p.inliers >= HIGH_CONFIDENCE])}
    excl_high = exclusions_from_pairs([p for p in pairs if p.inliers >= HIGH_CONFIDENCE])

    # how the cheap signals would have done against the geometric decision
    dup = k >= INLIER_THRESHOLD
    cheap = {}
    for thr in (0.97, 0.98, 0.99, 0.995):
        sel = c >= thr
        cheap[f"cosine>={thr}"] = {"pairs": int(sel.sum()), "verified": int((sel & dup).sum())}
    for thr in (0, 2, 4, 6, 8):
        sel = h <= thr
        cheap[f"hamming<={thr}"] = {"pairs": int(sel.sum()), "verified": int((sel & dup).sum())}
    cheap["verified_pairs_cosine_quantiles"] = [round(float(q), 4) for q in np.quantile(c[dup], [0, 0.1, 0.5])] if dup.any() else []
    cheap["verified_pairs_hamming_quantiles"] = [int(q) for q in np.quantile(h[dup], [0.5, 0.9, 1.0])] if dup.any() else []

    result = {
        "rule": f"same eye if RANSAC inliers >= {INLIER_THRESHOLD} (all {len(c)} pairs checked)",
        "inlier_histogram_all_pairs": {str(t): int((k >= t).sum()) for t in (5, 8, 10, 12, 15, 20, 30, 50, 100)},
        "inlier_histogram_cross_split": {str(t): int((k[cross] >= t).sum()) for t in (5, 8, 10, 12, 15, 20, 30, 50, 100)},
        "by_split_pair": by_split,
        "excluded": {s: len(v) for s, v in excl.items()},
        f"excluded_if_threshold_were_{HIGH_CONFIDENCE}": {s: len(v) for s, v in excl_high.items()},
        "images_in_any_pair": len({x for p in pairs for x in (p.a, p.b)}),
        "cheap_signals_vs_geometric": cheap,
        "seconds": {"features": round(t_feat, 1), "matching": round(t_match, 1), "total": round(time.perf_counter() - t0, 1)},
        "pairs": [asdict(p) for p in pairs],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dedup_pairs.json").write_text(json.dumps(result, indent=1))
    exclusions_path.parent.mkdir(parents=True, exist_ok=True)
    exclusions_path.write_text(
        json.dumps(
            {
                "about": "RFMiD 1.0 images excluded from 'deduplicated' evaluations: each shows the same eye as an "
                f"image in an earlier official split (train for val; train or val for test), by a geometric match of "
                f"the retina (>= {INLIER_THRESHOLD} RANSAC inliers). Generated by `python -m eye_rag.dedup`; "
                "see docs/DATA.md, 'Duplicate audit'. The official split itself is unchanged.",
                "rule": result["rule"],
                "exclude": excl,
            },
            indent=1,
        )
        + "\n"
    )
    return result


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path("runs"))
    a = p.parse_args(argv)
    r = run(a.out)
    print(json.dumps({k: v for k, v in r.items() if k != "pairs"}, indent=1))
    print(f"wrote {EXCLUSIONS}", file=sys.stderr)


if __name__ == "__main__":
    main()

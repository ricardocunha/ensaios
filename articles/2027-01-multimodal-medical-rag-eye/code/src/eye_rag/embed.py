"""BiomedCLIP image and text embeddings, cached on disk.

Model: `microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224` through open_clip
(MIT licence; the model card limits intended use to research). Vectors are L2-normalised,
so a dot product is the cosine similarity.

    uv run python -m eye_rag.embed            # embeds train/val/test into data/embeddings/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

MODEL_ID = "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
CACHE = Path("data/embeddings")
TEMPLATES = (
    "a color fundus photograph showing {}.",
    "a retinal fundus image with {}.",
    "fundus photography of an eye with {}.",
)


def pick_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


def normalize(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=-1, keepdims=True).clip(min=1e-12)


class BiomedCLIP:
    """Thin wrapper: load once, embed images (paths) and texts in batches."""

    def __init__(self, device: str | None = None):
        import open_clip
        import torch

        torch.manual_seed(0)
        self.device = device or pick_device()
        self.model, self.preprocess = open_clip.create_model_from_pretrained(MODEL_ID)
        self.tokenizer = open_clip.get_tokenizer(MODEL_ID)
        self.model = self.model.to(self.device).eval()
        self.logit_scale = float(self.model.logit_scale.exp().item())

    def images(self, paths: Sequence[Path], batch: int = 64) -> np.ndarray:
        import torch
        from PIL import Image

        out = []
        for i in range(0, len(paths), batch):
            x = torch.stack([self.preprocess(Image.open(p).convert("RGB")) for p in paths[i : i + batch]])
            with torch.no_grad():
                out.append(self.model.encode_image(x.to(self.device)).float().cpu().numpy())
        return normalize(np.concatenate(out))

    def texts(self, texts: Sequence[str], batch: int = 128) -> np.ndarray:
        import torch

        out = []
        for i in range(0, len(texts), batch):
            t = self.tokenizer(list(texts[i : i + batch]), context_length=256).to(self.device)
            with torch.no_grad():
                out.append(self.model.encode_text(t).float().cpu().numpy())
        return normalize(np.concatenate(out))


def cached(
    name: str,
    ids: Sequence[str],
    compute: Callable[[], np.ndarray],
    cache: Path = CACHE,
    meta: dict | None = None,
) -> np.ndarray:
    """Return vectors for `ids` from `cache/name.npz`, computing and saving them on a miss.
    A miss is anything but exactly these ids, in this order, for the same model and `meta`."""
    path = cache / f"{name}.npz"
    meta = {"model": MODEL_ID, **(meta or {})}
    if path.exists():
        z = np.load(path, allow_pickle=False)
        if list(z["ids"]) == list(ids) and json.loads(str(z["meta"])) == meta:
            return z["vectors"]
    vectors = compute()
    if len(vectors) != len(ids):
        raise ValueError(f"{name}: {len(vectors)} vectors for {len(ids)} ids")
    cache.mkdir(parents=True, exist_ok=True)
    np.savez(path, ids=np.array(ids), vectors=vectors.astype(np.float32), meta=json.dumps(meta))
    return vectors.astype(np.float32)


def image_embeddings(split: str, model: BiomedCLIP | None = None, cache: Path = CACHE) -> tuple[list, np.ndarray]:
    """(records, vectors) for one RFMiD split, using the cache when possible."""
    from eye_rag.rfmid import LONG_SIDE, load_split

    records = load_split(split)
    holder = {}

    def compute():
        m = model or holder.setdefault("m", BiomedCLIP())
        t = time.perf_counter()
        v = m.images([r.path for r in records])
        print(f"embedded {len(records)} {split} images in {time.perf_counter() - t:.1f}s on {m.device}", file=sys.stderr)
        return v

    vecs = cached(f"rfmid_{split}_image", [r.id for r in records], compute, cache, {"long_side": LONG_SIDE})
    return records, vecs


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--splits", nargs="+", default=["train", "val", "test"])
    a = p.parse_args(argv)
    model = BiomedCLIP()
    for s in a.splits:
        recs, v = image_embeddings(s, model)
        print(f"{s}: {v.shape}")


if __name__ == "__main__":
    main()

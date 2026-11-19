"""Downloads the router's embedding model at a pinned revision and verifies
each file's sha256. Standard library only: the image runs it as a plain script
in its own layer, cached until the pins change.

    python -m keelgw_router.fetch_model [DIR]   # default .cache/model
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

# The embedding model, pinned to a Hugging Face commit. Its card's license
# metadata is MIT. Each file's sha256 is checked after download.
MODEL_REPO = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MODEL_FILES = {
    "onnx/model.onnx": "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665",
    "onnx/tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
}


def fetch(dest: Path) -> Path:
    """Downloads MODEL_FILES at MODEL_REVISION into dest, verifying each
    file's sha256. Files already there with the right hash are kept."""
    for name, want in MODEL_FILES.items():
        path = dest / name
        if path.exists() and sha256(path) == want:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
        tmp = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url, timeout=600) as resp, tmp.open("wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        got = sha256(tmp)
        if got != want:
            tmp.unlink()
            raise SystemExit(f"fetch: {name} has sha256 {got}, want {want}")
        tmp.rename(path)
        print(f"fetch: {name} verified", file=sys.stderr)
    return dest


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    # Default: the project root's .cache (src/keelgw_router/ is two levels down).
    fetch(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / ".cache" / "model")

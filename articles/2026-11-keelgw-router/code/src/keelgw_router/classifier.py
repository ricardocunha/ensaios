"""The router's classifier.

A small multilingual embedding model, intfloat/multilingual-e5-small (MIT,
pinned in fetch_model.py), turns a prompt into a 384-dim vector on CPU through ONNX
Runtime; keelgw's four-Tier head (multinomial logistic regression, numpy
weights in model/head.json) turns the vector into Tier probabilities.

train.py and server.py share everything here, so a prompt is prepared the same
way for training and for serving.

The embedding model's pins and download live in fetch_model.py (standard
library only, so the image fetches the model in its own cached layer).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .fetch_model import MODEL_FILES, MODEL_REPO, MODEL_REVISION, fetch  # noqa: F401 (re-exported)

TIERS = ("simple", "medium", "complex", "reasoning")

DIM = 384

# e5 expects a "query: " prefix on every input; for features used by a
# classifier the model card says to use "query: ".
PREFIX = "query: "
# Tokens read per prompt, two of them <s> and </s>. The model can take 512, but
# reading 256 costs no accuracy on our data (80.5% eval against 80.2%; 99% of
# the labelled prompts fit whole) and a full-length input takes under half the
# time (20 ms against 47 ms natively), which is what saturated the router under
# load (keelgw's load tests, 2026-10-09).
MAX_TOKENS = 256
# When the latest user turn alone is too long, its first HEAD_TOKENS tokens and
# as much of its end as fits are kept: the ask is usually at the start or the
# end of a pasted block.
HEAD_TOKENS = 96
# Characters looked at per field, before tokenising: bounds the tokenizer's work
# (keelgw's gateway already sends at most 8 000 characters).
MAX_CHARS = 16_000

# The project root (code/): src/keelgw_router/classifier.py is two levels down.
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache"
HEAD = ROOT / "model" / "head.json"


class Embedder:
    """multilingual-e5-small on ONNX Runtime: mean pooling over the attention
    mask, then L2 normalisation, as the model card specifies."""

    def __init__(self, model_dir: Path, threads: int = 0):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.tok = Tokenizer.from_file(str(model_dir / "onnx/tokenizer.json"))
        self.tok.no_truncation()
        self.tok.no_padding()
        self.bos, self.eos = self.tok.token_to_id("<s>"), self.tok.token_to_id("</s>")
        self.prefix = self.tok.encode(PREFIX, add_special_tokens=False).ids
        ort.set_default_logger_severity(3)  # errors only
        opts = ort.SessionOptions()
        # Prepacked weight copies cost about 50 MB and bought no speed here.
        opts.add_session_config_entry("session.disable_prepacking", "1")
        if threads:
            opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(model_dir / "onnx/model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def ids(self, text: str) -> list[int]:
        """The model's input for a prompt; see prepare()."""
        return prepare(self.prefix, self.tok.encode(cap(text), add_special_tokens=False).ids, self.bos, self.eos)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.embed_ids([self.ids(t) for t in texts])

    def embed_ids(self, rows: list[list[int]]) -> np.ndarray:
        n = max(len(r) for r in rows)
        ids = np.zeros((len(rows), n), dtype=np.int64)  # <pad> is 1 for XLM-R, but masked out anyway
        mask = np.zeros((len(rows), n), dtype=np.int64)
        for i, r in enumerate(rows):
            ids[i, : len(r)] = r
            mask[i, : len(r)] = 1
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.sess.run(None, feed)[0]  # last_hidden_state: (batch, tokens, 384)
        m = mask[..., None].astype(np.float32)
        pooled = (hidden * m).sum(axis=1) / np.maximum(m.sum(axis=1), 1.0)
        return pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)

    def explain(self, text: str, head: Head) -> tuple[list[float], dict]:
        """Classifies one prompt as ids(), embed() and Head.probs() do, and
        reports each step's counts and timings: the live test's verbose output.
        The token pieces are the caller's own prompt, so they go back only to
        that caller and are never logged."""
        t0 = time.perf_counter()
        turn = cap(text)
        enc = self.tok.encode(turn, add_special_tokens=False)
        t1 = time.perf_counter()
        ids = prepare(self.prefix, enc.ids, self.bos, self.eos)
        room = MAX_TOKENS - 2 - len(self.prefix)
        kept = len(ids) - 2 - len(self.prefix)
        t2 = time.perf_counter()
        x = self.embed_ids([ids])
        t3 = time.perf_counter()
        logits = x @ head.weights.T + head.bias
        probs = softmax(logits)[0]
        t4 = time.perf_counter()
        pieces = enc.tokens
        return probs.tolist(), {
            "prepare": {
                "chars": len(text),
                "chars_capped": len(text) > MAX_CHARS,
                "chars_read": len(turn),
                "prefix": PREFIX,
                "prefix_tokens": len(self.prefix),
                "turn_tokens": len(enc.ids),
                "room": room,
                "truncated": len(enc.ids) > room,
                "dropped_tokens": len(enc.ids) - kept,
                "model_tokens": len(ids),
                "max_tokens": MAX_TOKENS,
                "pieces": pieces if len(pieces) <= 40 else [*pieces[:20], "…", *pieces[-20:]],
                "ms": round((t2 - t0) * 1000, 2),
                "tokenise_ms": round((t1 - t0) * 1000, 2),
            },
            "embed": {
                "model": MODEL_REPO,
                "layers": 12,
                "hidden": [len(ids), DIM],
                "dim": int(x.shape[1]),
                "norm": round(float(np.linalg.norm(x[0])), 4),
                "first": [round(float(v), 4) for v in x[0, :4]],
                "ms": round((t3 - t2) * 1000, 2),
            },
            "decide": {
                "weights": list(head.weights.shape),
                "parameters": int(head.weights.size + head.bias.size),
                "logits": {t: round(float(z), 3) for t, z in zip(TIERS, logits[0], strict=True)},
                "ms": round((t4 - t3) * 1000, 3),
            },
        }


def cap(text: str) -> str:
    """At most MAX_CHARS characters: the first quarter and the last three quarters."""
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS // 4] + "\n" + text[-(MAX_CHARS * 3 // 4) :]


def prepare(prefix: list[int], turn: list[int], bos: int, eos: int) -> list[int]:
    """The truncation policy. The model reads MAX_TOKENS tokens:
    <s> "query: " <latest user turn> </s>.

    Only the latest user turn is classified; when it is too long, its first
    HEAD_TOKENS tokens and its last tokens are kept.

    Earlier conversation is deliberately left out. The head is trained on single
    prompts, and the embedding is a mean over every token read, so earlier turns
    outweigh a short new ask. Measured on the eval set (2026-10-09): 80.0%
    accuracy on the turn alone, 43% with three earlier turns appended (38% when
    they were reasoning turns: a simple ask was then right 2% of the time), and
    seven times the inference time. A head that uses context needs training
    data with context."""
    room = MAX_TOKENS - 2 - len(prefix)
    if len(turn) > room:
        turn = turn[:HEAD_TOKENS] + turn[len(turn) - (room - HEAD_TOKENS) :]
    return [bos, *prefix, *turn, eos]


@dataclass
class Head:
    """Multinomial logistic regression over the embedding: softmax(Wx + b)."""

    weights: np.ndarray  # (len(TIERS), DIM)
    bias: np.ndarray  # (len(TIERS),)
    meta: dict

    @classmethod
    def load(cls, path: Path = HEAD) -> Head:
        d = json.loads(path.read_text())
        if tuple(d["tiers"]) != TIERS:
            raise ValueError(f"{path}: Tiers {d['tiers']}, want {list(TIERS)}")
        if d.get("model_revision") != MODEL_REVISION:
            raise ValueError(f"{path}: trained on {d.get('model_revision')}, this build embeds with {MODEL_REVISION}")
        w, b = np.asarray(d["weights"], dtype=np.float32), np.asarray(d["bias"], dtype=np.float32)
        if w.shape != (len(TIERS), DIM) or b.shape != (len(TIERS),):
            raise ValueError(f"{path}: weights {w.shape}, bias {b.shape}")
        return cls(w, b, {k: v for k, v in d.items() if k not in ("weights", "bias")})

    def save(self, path: Path = HEAD) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        d = dict(self.meta)
        d.update(
            tiers=list(TIERS),
            model_repo=MODEL_REPO,
            model_revision=MODEL_REVISION,
            weights=[[round(float(x), 6) for x in row] for row in self.weights],
            bias=[round(float(x), 6) for x in self.bias],
        )
        path.write_text(json.dumps(d, indent=1) + "\n")

    def probs(self, x: np.ndarray) -> np.ndarray:
        return softmax(x @ self.weights.T + self.bias)


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)

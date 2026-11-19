"""The real embedding model and the shipped head, in process: no HTTP, no API.

Needs the pinned model in .cache/model (`make model` downloads and verifies it).
The accuracy checks allow one point either way: ONNX Runtime's float results
differ slightly between CPUs (arm64 against x86).
"""

from __future__ import annotations

import json

import pytest

from keelgw_router import classifier as c
from keelgw_router import fetch_model, train

pytestmark = pytest.mark.model

METRICS = json.loads((c.ROOT / "model" / "metrics.json").read_text())
TOLERANCE = 0.01
MODEL_DIR = c.CACHE / "model"


@pytest.fixture(scope="module")
def embedder() -> c.Embedder:
    if not all((MODEL_DIR / name).exists() for name in fetch_model.MODEL_FILES):
        pytest.fail(f"no model in {MODEL_DIR}; run `make model` first")
    return c.Embedder(MODEL_DIR, threads=2)


@pytest.fixture(scope="module")
def head() -> c.Head:
    return c.Head.load()


def test_model_files_match_their_pinned_sha256(embedder):
    for name, want in fetch_model.MODEL_FILES.items():
        assert fetch_model.sha256(MODEL_DIR / name) == want, name


def test_the_head_was_trained_on_this_model_revision(head):
    assert head.meta["model_revision"] == c.MODEL_REVISION
    assert head.meta.get("provisional") is False


def test_a_clear_cut_prompt_per_tier(embedder, head, prompts):
    for tier, p in prompts["tiers"].items():
        probs = head.probs(embedder.embed([p["text"]]))[0]
        assert c.TIERS[probs.argmax()] == tier, (tier, probs.round(3).tolist())
        assert probs.max() > 0.9, (tier, probs.round(3).tolist())


def test_portuguese_is_understood(embedder, head, prompts):
    probs = head.probs(embedder.embed([prompts["portuguese_simple"]]))[0]
    assert c.TIERS[probs.argmax()] == "simple", probs.round(3).tolist()


def test_a_long_prompt_is_cut_to_the_tokens_the_model_reads(embedder):
    ids = embedder.ids("why does this fail?\n" + "Traceback (most recent call last):\n  File 'app.py', line 3\n" * 3000)
    assert len(ids) == c.MAX_TOKENS
    assert ids[0] == embedder.bos and ids[-1] == embedder.eos


def test_eval_accuracy_matches_metrics_json(embedder, head):
    rows = [r for r in train.load_prompts() if r["split"] == "eval"]
    assert len(rows) == METRICS["eval"]["n"]
    x = train.embed_cached(embedder.embed, [r["text"] for r in rows])
    pred = head.probs(x).argmax(axis=1)
    acc = sum(c.TIERS[p] == r["tier"] for p, r in zip(pred, rows, strict=True)) / len(rows)
    assert abs(acc - METRICS["eval"]["accuracy"]) <= TOLERANCE, (acc, METRICS["eval"]["accuracy"])


def test_retraining_from_the_dataset_reproduces_the_head(embedder):
    # About 4,200 prompts: the first run embeds them all (a minute or two on a
    # laptop); the embeddings are cached in .cache/embeddings after that.
    head, m = train.train(train.load_prompts(), embedder.embed)
    assert m["l2"] == METRICS["l2"]
    assert m["rows"] == METRICS["rows"]
    assert abs(m["eval"]["accuracy"] - METRICS["eval"]["accuracy"]) <= TOLERANCE, (
        m["eval"]["accuracy"],
        METRICS["eval"]["accuracy"],
    )

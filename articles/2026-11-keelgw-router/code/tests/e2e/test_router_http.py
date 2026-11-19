"""The router image from the outside, over HTTP, as a gateway would call it.

`make e2e` builds the image, starts both services with docker compose and runs
these from a container on the compose network. Against services you started
yourself (`make up`), `uv run pytest -m e2e` reaches them on localhost:18080
and localhost:18081.

    router        the normal settings: concurrency 1, a 1,000 ms queue
    router-tight  concurrency 1, a 50 ms queue, 1 thread: made to be busy
"""

from __future__ import annotations

import http.client
import json
import re
import statistics
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.e2e

TIERS = ("simple", "medium", "complex", "reasoning")
PINNED_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
MAX_BODY = 64 * 1024
# A prompt that fills all 256 tokens the model reads: the slowest inference.
FULL_LENGTH = "why does this fail?\n" + "Traceback (most recent call last):\n  File 'app.py', line 3, in <module>\n" * 300


def call(base: str, path: str, body=None, raw: bytes | None = None, method: str | None = None, timeout: float = 10):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def classify(base: str, text: str, **extra) -> tuple[int, dict]:
    code, body = call(base, "/v1/classify", {"text": text, **extra})
    return code, json.loads(body)


def metric(base: str, name: str) -> float:
    _, text = call(base, "/metrics")
    total = 0.0
    for line in text.splitlines():
        if line.startswith(name) and not line.startswith("#"):
            total += float(line.rsplit(" ", 1)[1])
    return total


# ---- health and the pinned model ----------------------------------------------------


def test_health_reports_the_pinned_model_and_a_final_head(router_url):
    code, body = call(router_url, "/healthz")
    h = json.loads(body)
    assert code == 200 and h["status"] == "ok"
    assert h["model"] == "intfloat/multilingual-e5-small"
    assert h["model_revision"] == PINNED_REVISION
    assert h["provisional"] == "false"
    assert h["trained_at"]


# ---- classification -----------------------------------------------------------------


@pytest.mark.parametrize("tier", TIERS)
def test_a_clear_cut_prompt_lands_in_its_tier(router_url, prompts, tier):
    code, got = classify(router_url, prompts["tiers"][tier]["text"])
    assert code == 200, got
    assert got["tier"] == tier, got


def test_the_response_has_four_scores_that_sum_to_one(router_url, prompts):
    _, got = classify(router_url, prompts["tiers"]["medium"]["text"])
    assert set(got["scores"]) == set(TIERS)
    assert abs(sum(got["scores"].values()) - 1) < 0.01
    assert got["tier"] == max(got["scores"], key=got["scores"].get)
    assert 0 < got["latency_ms"] < 1500


def test_portuguese(router_url, prompts):
    code, got = classify(router_url, prompts["portuguese_simple"])
    assert (code, got["tier"]) == (200, "simple"), got


def test_earlier_conversation_is_ignored(router_url, prompts):
    # Only the latest turn is classified; an extra field must not change the answer.
    text = prompts["tiers"]["simple"]["text"]
    _, alone = classify(router_url, text)
    _, with_context = classify(router_url, text, context="user: prove this lock-free queue is linearizable")
    assert alone["tier"] == with_context["tier"] == "simple"
    assert alone["scores"] == with_context["scores"]


def test_a_long_prompt_under_the_body_limit_is_classified(router_url):
    # The limit is on the JSON body, so trim until the encoded body fits.
    text = (FULL_LENGTH * 4)[:MAX_BODY]
    while len(json.dumps({"text": text}).encode()) > MAX_BODY - 64:
        text = text[:-512]
    code, got = classify(router_url, text)
    assert code == 200 and got["tier"] in TIERS, got


# ---- refusals ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, raw, want",
    [
        ({"text": ""}, None, 400),
        ({"text": "   "}, None, 400),
        ({"text": 42}, None, 400),
        ({"prompt": "rename x"}, None, 400),
        (None, b"not json", 400),
        ({"text": "x" * (MAX_BODY + 1)}, None, 413),
    ],
    ids=["empty", "blank", "not-a-string", "no-text-field", "not-json", "over-64KiB"],
)
def test_bad_requests_are_refused(router_url, body, raw, want):
    code, resp = call(router_url, "/v1/classify", body, raw=raw)
    assert code == want, resp
    assert "error" in json.loads(resp)


def test_unknown_paths_are_404(router_url):
    assert call(router_url, "/v1/other", {"text": "x"})[0] == 404
    assert call(router_url, "/v1/classify")[0] == 404  # GET


# ---- connections, concurrency and latency ---------------------------------------------


def test_requests_share_a_kept_alive_connection(router_url, prompts):
    u = urlsplit(router_url)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=10)
    try:
        for tier in ("simple", "complex"):
            conn.request("POST", "/v1/classify", body=json.dumps({"text": prompts["tiers"][tier]["text"]}),
                         headers={"Content-Type": "application/json"})  # fmt: skip
            resp = conn.getresponse()
            assert (resp.status, json.loads(resp.read())["tier"]) == (200, tier)
    finally:
        conn.close()


def test_parallel_requests_queue_and_all_succeed(router_url, prompts):
    # One inference at a time, but a 1,000 ms queue: eight at once all get through.
    texts = [p["text"] for p in prompts["tiers"].values()] * 2
    results: list[int] = []
    barrier = threading.Barrier(len(texts))

    def worker(text):
        barrier.wait()
        results.append(classify(router_url, text)[0])

    threads = [threading.Thread(target=worker, args=(t,)) for t in texts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * len(texts)


def test_latency_is_within_budget(router_url, prompts):
    # keelgw's target is p95 under 800 ms; the gateway gives up at 1,500 ms.
    texts = [p["text"] for p in prompts["tiers"].values()] * 5 + [FULL_LENGTH] * 5
    wall, inference = [], []
    for text in texts:
        t0 = time.perf_counter()
        _, got = classify(router_url, text)
        wall.append((time.perf_counter() - t0) * 1000)
        inference.append(got["latency_ms"])
    p95 = statistics.quantiles(wall, n=20)[-1]
    print(f"\nlatency over {len(texts)} requests: wall p50 {statistics.median(wall):.1f} ms, p95 {p95:.1f} ms; "
          f"inference p50 {statistics.median(inference):.1f} ms")  # fmt: skip
    assert p95 < 800


# ---- metrics ------------------------------------------------------------------------


def test_metrics_count_requests_and_classifications(router_url, prompts):
    before_ok = metric(router_url, 'keelgw_router_requests_total{code="200"}')
    before_bad = metric(router_url, 'keelgw_router_requests_total{code="400"}')
    before_simple = metric(router_url, 'keelgw_router_classifications_total{tier="simple"}')
    classify(router_url, prompts["tiers"]["simple"]["text"])
    call(router_url, "/v1/classify", {"text": ""})
    assert metric(router_url, 'keelgw_router_requests_total{code="200"}') == before_ok + 1
    assert metric(router_url, 'keelgw_router_requests_total{code="400"}') == before_bad + 1
    assert metric(router_url, 'keelgw_router_classifications_total{tier="simple"}') == before_simple + 1
    _, text = call(router_url, "/metrics")
    assert re.search(r"^keelgw_router_inference_seconds_count \d+$", text, re.M)
    assert f'model_revision="{PINNED_REVISION}"' in text


# ---- busy: router-tight -----------------------------------------------------------------


def test_a_busy_router_answers_503_fast_and_recovers(tight_url, prompts):
    # 16 full-length prompts at once against one slot and a 50 ms queue: some
    # are served, the rest are told "busy" at once, which is what lets the
    # gateway fall back to its Fallback Tier instead of waiting out 1,500 ms.
    n = 16
    results: list[tuple[int, float]] = []
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()
        t0 = time.perf_counter()
        code, _ = call(tight_url, "/v1/classify", {"text": FULL_LENGTH})
        results.append((code, time.perf_counter() - t0))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    codes = sorted(c for c, _ in results)
    assert 200 in codes and 503 in codes, codes
    assert set(codes) <= {200, 503}, codes
    busy = sorted(s for c, s in results if c == 503)
    print(f"\nbusy: {codes.count(200)} served, {len(busy)} answered 503 in {busy[0]:.2f}-{busy[-1]:.2f} s")
    assert busy[-1] < 1.5, "a 503 must come back before the gateway's 1.5 s cutoff"
    assert metric(tight_url, 'keelgw_router_requests_total{code="503"}') >= codes.count(503)
    # Once the burst is over, it serves again.
    code, got = classify(tight_url, prompts["tiers"]["reasoning"]["text"])
    assert (code, got["tier"]) == (200, "reasoning")

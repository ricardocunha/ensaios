"""Unit tests for classifier.py, train.py and server.py: no network, no model.

A fake embedder stands in for multilingual-e5-small, so these run in seconds;
the real model is exercised by tests/model.
"""

import hashlib
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr
from pathlib import Path

import numpy as np

from keelgw_router import classifier as c
from keelgw_router import server, train

# Words that mark each Tier in the synthetic fixture.
MARKS = {
    "simple": ["rename", "format", "typo", "lookup"],
    "medium": ["implement", "explain", "test", "fix"],
    "complex": ["refactor across", "migrate", "debug flaky", "review design"],
    "reasoning": ["prove", "lock-free", "algorithm", "threat model"],
}
DIRS = np.random.default_rng(1).normal(size=(len(c.TIERS), c.DIM))


def fake_embed(texts):
    """A tiny stand-in embedding: the Tier's direction for each mark word in
    the text, plus noise from the text's hash; L2-normalised like e5."""
    out = []
    for t in texts:
        seed = int(hashlib.sha256(t.encode()).hexdigest()[:8], 16)
        v = np.random.default_rng(seed).normal(scale=0.6, size=c.DIM)
        for i, tier in enumerate(c.TIERS):
            if any(m in t for m in MARKS[tier]):
                v += DIRS[i]
        out.append(v / np.linalg.norm(v))
    return np.asarray(out, dtype=np.float32)


def fixture(n_per_tier=60, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for tier in c.TIERS:
        for i in range(n_per_tier):
            mark = MARKS[tier][i % 4]
            split = "eval" if i % 5 == 0 else "val" if i % 5 == 1 else "train"
            rows.append({"text": f"please {mark} item {i} {rng.integers(1e6)}", "tier": tier, "split": split})
    return rows


class Truncation(unittest.TestCase):
    BOS, EOS, PREFIX = 0, 2, [41, 1294, 12]

    def ids(self, turn):
        return c.prepare(self.PREFIX, list(turn), self.BOS, self.EOS)

    def test_short_prompt_is_kept_whole_with_prefix(self):
        self.assertEqual(self.ids([7, 8]), [0, 41, 1294, 12, 7, 8, 2])

    def test_never_more_than_the_model_reads(self):
        # Prefix (3) plus BOS and EOS: a turn of MAX_TOKENS - 5 fits exactly.
        edge = c.MAX_TOKENS - 5
        for turn in (5000, 10, edge - 1, edge, edge + 1):
            self.assertEqual(len(self.ids(range(turn))), min(c.MAX_TOKENS, 2 + 3 + turn))

    def test_long_turn_keeps_its_start_and_end(self):
        got = self.ids(range(1000))[1 + 3 : -1]
        self.assertEqual(got[: c.HEAD_TOKENS], list(range(c.HEAD_TOKENS)))
        self.assertEqual(got[-1], 999, "the end of the latest turn")


class HeadFile(unittest.TestCase):
    def test_round_trip_and_revision_check(self):
        p = Path(tempfile.mkdtemp()) / "head.json"
        h = c.Head(np.ones((4, c.DIM), np.float32), np.arange(4, dtype=np.float32), {"provisional": True})
        h.save(p)
        got = c.Head.load(p)
        self.assertTrue(got.meta["provisional"])
        self.assertEqual(got.probs(np.zeros((1, c.DIM))).argmax(), 3)
        d = json.loads(p.read_text())
        d["model_revision"] = "0" * 40
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            c.Head.load(p)


class Training(unittest.TestCase):
    def setUp(self):
        self.cache = Path(tempfile.mkdtemp())

    def test_learns_the_fixture_and_reports(self):
        rows = fixture()
        head, m = train.train(rows, fake_embed, cache_dir=self.cache)
        e = m["eval"]
        self.assertGreaterEqual(e["accuracy"], 0.9, e)
        self.assertEqual(set(e["per_tier"]), set(c.TIERS))
        self.assertEqual(sum(map(sum, e["confusion"]["matrix"])), e["n"])
        self.assertEqual(m["rows"]["eval"]["simple"], 12)
        self.assertIn(m["l2"], train.L2_GRID)
        self.assertEqual(sum(f["n"] for f in m["eval_by_form"].values()), e["n"])

    def test_embeddings_are_cached(self):
        rows, calls = fixture(10), []

        def counting(texts):
            calls.append(len(texts))
            return fake_embed(texts)

        train.train(rows, counting, cache_dir=self.cache)
        first = sum(calls)
        train.train(rows, counting, cache_dir=self.cache)
        self.assertEqual(first, len(rows))
        self.assertEqual(sum(calls), first, "second run embedded again")

    def test_a_missing_tier_is_never_predicted(self):
        rows = [r for r in fixture() if r["tier"] != "reasoning"]
        head, m = train.train(rows, fake_embed, cache_dir=self.cache)
        self.assertNotIn("reasoning", m["eval"]["per_tier"])
        self.assertTrue((head.probs(fake_embed(["prove it", "rename x"])).argmax(axis=1) != 3).all())

    def test_report(self):
        r = train.report(np.array([0, 0, 1, 2]), np.array([0, 1, 1, 2]))
        self.assertEqual(
            (r["accuracy"], r["per_tier"]["simple"]["accuracy"], r["per_tier"]["medium"]["precision"]), (0.75, 0.5, 0.5)
        )
        self.assertAlmostEqual(r["macro_f1"], round((2 / 3 + 2 / 3 + 1) / 3, 4))

    def test_latency_is_per_request(self):
        seen = []
        lat = train.latency(lambda t: seen.append(t), ["a", "b", "c"], warmup=1)
        self.assertEqual((lat["n"], seen), (3, ["a", "a", "b", "c"]))

    def test_provisional_rows_from_the_generators_raw_answers(self):
        from keelgw_router import dataset

        cell = dataset.cells()[0]
        raw = Path(tempfile.mkdtemp()) / "raw.jsonl"
        content = json.dumps({"prompts": [{"text": f"rename thing {i}", "note": ""} for i in range(30)]})
        raw.write_text(json.dumps({"custom_id": cell.custom_id, "content": content}) + "\n" + '{"custom_id": "nope"}\n')
        rows = train.load_generated(raw)
        self.assertEqual(len(rows), 30)
        self.assertTrue(all(r["tier"] == cell.tier for r in rows))
        self.assertEqual({r["split"] for r in rows} <= {"train", "val", "eval"}, True)

    def test_prompts_rows_need_a_tier_and_a_split(self):
        p = Path(tempfile.mkdtemp()) / "prompts.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in [
            {"text": "a", "tier": "simple", "split": "train"},
            {"text": "b", "tier": "simple", "split": "review"},
            {"text": "c", "tier": "huge", "split": "eval"},
        ]))  # fmt: skip
        self.assertEqual([r["text"] for r in train.load_prompts(p)], ["a"])


class Server(unittest.TestCase):
    def start(self, classify, **kw):
        r = server.Router(classify, {"model_revision": "x", "provisional": "true"}, **kw)
        srv = server.serve(r, 0)[0]
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.base = f"http://127.0.0.1:{srv.server_address[1]}"
        return r

    def call(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_classify(self):
        seen = []
        self.start(lambda t: seen.append(t) or [0.1, 0.2, 0.6, 0.1])
        code, body = self.call("/v1/classify", {"text": "refactor the module"})
        got = json.loads(body)
        self.assertEqual((code, got["tier"], got["scores"]["complex"]), (200, "complex", 0.6))
        self.assertIn("latency_ms", got)
        self.assertEqual(seen, ["refactor the module"])

    def test_earlier_conversation_is_never_classified(self):
        # An older gateway may still send "context"; it must not reach the model.
        seen = []
        self.start(lambda t: seen.append(t) or [0.7, 0.1, 0.1, 0.1])
        code, _ = self.call("/v1/classify", {"text": "rename x", "context": "user: prove this lock-free queue is linearizable"})
        self.assertEqual((code, seen), (200, ["rename x"]))

    def test_responses_are_not_held_back_by_nagle(self):
        # Without TCP_NODELAY every response on a kept-alive connection waited
        # about 40 ms for the client's delayed ACK (measured in the cluster; it
        # doesn't reproduce on a macOS loopback, so the setting is pinned here).
        r = self.start(lambda t: [1, 0, 0, 0])
        self.assertTrue(server.handler(r).disable_nagle_algorithm)

    def test_chunked_body(self):
        import http.client

        self.start(lambda t: [0, 1, 0, 0])
        conn = http.client.HTTPConnection(self.base.removeprefix("http://"), timeout=5)
        conn.request("POST", "/v1/classify", body=iter([b'{"text": "expl', b'ain this"}']), encode_chunked=True)
        resp = conn.getresponse()
        self.assertEqual((resp.status, json.loads(resp.read())["tier"]), (200, "medium"))
        conn.request("POST", "/v1/classify", body=iter([b"x" * server.MAX_BODY, b"y"]), encode_chunked=True)
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()

    def test_bad_requests(self):
        self.start(lambda t: [1, 0, 0, 0])
        for body in ({"text": ""}, {"text": 3}, {"nope": "x"}):
            self.assertEqual(self.call("/v1/classify", body)[0], 400, body)
        self.assertEqual(self.call("/v1/classify", raw=b"not json")[0], 400)
        self.assertEqual(self.call("/v1/classify", {"text": "x" * (server.MAX_BODY + 1)})[0], 413)
        self.assertEqual(self.call("/v1/other", {"text": "x"})[0], 404)

    def test_bodies_that_could_stall_the_connection(self):
        import http.client
        import socket

        self.start(lambda t: [1, 0, 0, 0])
        host, port = self.base.removeprefix("http://").split(":")
        # A negative length would otherwise read until the client hangs up.
        with socket.create_connection((host, int(port)), timeout=5) as s:
            s.sendall(b"POST /v1/classify HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n")
            self.assertIn(b" 400 ", s.recv(4096))
        # A 404 leaves its body unread, so the connection is closed rather than
        # reading that body as the next request.
        conn = http.client.HTTPConnection(host, int(port), timeout=5)
        conn.request("POST", "/v1/other", body=b'{"text": "x"}')
        resp = conn.getresponse()
        resp.read()
        self.assertEqual((resp.status, resp.getheader("Connection")), (404, "close"))
        conn.close()
        self.assertEqual(server.handler(server.Router(lambda t: [], {})).timeout, 120)

    def test_a_head_with_the_wrong_number_of_tiers_is_a_500(self):
        self.start(lambda t: [0.5, 0.5, 0])
        code, body = self.call("/v1/classify", {"text": "x"})
        self.assertEqual((code, json.loads(body)), (500, {"error": "classification failed"}))

    def test_health_and_metrics(self):
        self.start(lambda t: [0.7, 0.1, 0.1, 0.1])
        self.call("/v1/classify", {"text": "rename x"})
        self.call("/v1/classify", {"text": ""})
        code, health = self.call("/healthz")
        self.assertEqual((code, json.loads(health)["provisional"]), (200, "true"))
        _, m = self.call("/metrics")
        for want in (
            'keelgw_router_requests_total{code="200"} 1',
            'keelgw_router_requests_total{code="400"} 1',
            'keelgw_router_classifications_total{tier="simple"} 1',
            'keelgw_router_inference_seconds_bucket{le="+Inf"} 1',
            'keelgw_router_head_info{model_revision="x",provisional="true"} 1',
        ):
            self.assertIn(want, m)

    def test_busy_answers_503_instead_of_queueing_past_the_gateways_cutoff(self):
        gate = threading.Event()
        self.start(lambda t: gate.wait(5) and [1, 0, 0, 0], concurrency=1, queue_ms=100)
        first = threading.Thread(target=self.call, args=("/v1/classify", {"text": "slow"}))
        first.start()
        time.sleep(0.1)
        self.assertEqual(self.call("/v1/classify", {"text": "second"})[0], 503)
        gate.set()
        first.join()

    def test_a_failure_never_logs_the_prompt(self):
        def boom(text):
            raise RuntimeError(f"bad input {text}")

        self.start(boom)
        err = io.StringIO()
        with redirect_stderr(err):
            code, body = self.call("/v1/classify", {"text": "SECRET-PROMPT"})
        self.assertEqual(code, 500)
        self.assertNotIn("SECRET-PROMPT", err.getvalue() + body)


if __name__ == "__main__":
    unittest.main()

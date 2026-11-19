"""The router's HTTP service.

    POST /v1/classify {"text": "<latest user turn>"}
      -> {"tier": "medium", "scores": {"simple": 0.1, ...}, "latency_ms": 41.2}
    GET  /healthz   the model and head are loaded
    GET  /metrics   Prometheus text format

Standard library only, apart from the classifier itself. Prompt text is never
logged or kept: only counts and latencies are recorded.

Environment: PORT (8080), ROUTER_METRICS_PORT (also serve /metrics there),
ROUTER_MODEL_DIR (the pinned model files), ROUTER_HEAD (head.json),
ROUTER_THREADS (ONNX Runtime threads per inference, 2), ROUTER_CONCURRENCY
(inferences at once, 1), ROUTER_QUEUE_MS (how long a request may wait for its
turn before a 503, 1000: keelgw's gateway gives up at 1500 ms anyway).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import classifier as c

MAX_BODY = 64 * 1024
BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 3.0)

# classify(text) -> one probability per Tier, in c.TIERS order.
Classify = Callable[[str], "list[float]"]


class Metrics:
    def __init__(self, info: dict[str, str]):
        self.lock = threading.Lock()
        self.requests: dict[str, int] = {}
        self.tiers = dict.fromkeys(c.TIERS, 0)
        self.buckets = [0] * len(BUCKETS)
        self.count, self.sum = 0, 0.0
        self.info = info

    def request(self, code: int) -> None:
        with self.lock:
            self.requests[str(code)] = self.requests.get(str(code), 0) + 1

    def classified(self, tier: str, seconds: float) -> None:
        with self.lock:
            self.tiers[tier] += 1
            self.count += 1
            self.sum += seconds
            for i, b in enumerate(BUCKETS):
                if seconds <= b:
                    self.buckets[i] += 1

    def render(self) -> str:
        with self.lock:
            out = [
                "# HELP keelgw_router_requests_total Classify requests by HTTP status.",
                "# TYPE keelgw_router_requests_total counter",
                *(f'keelgw_router_requests_total{{code="{k}"}} {v}' for k, v in sorted(self.requests.items())),
                "# HELP keelgw_router_classifications_total Prompts classified, by Tier.",
                "# TYPE keelgw_router_classifications_total counter",
                *(f'keelgw_router_classifications_total{{tier="{t}"}} {n}' for t, n in self.tiers.items()),
                "# HELP keelgw_router_inference_seconds Time to classify one prompt (tokenise, embed, head).",
                "# TYPE keelgw_router_inference_seconds histogram",
                *(f'keelgw_router_inference_seconds_bucket{{le="{b}"}} {n}' for b, n in zip(BUCKETS, self.buckets, strict=True)),
                f'keelgw_router_inference_seconds_bucket{{le="+Inf"}} {self.count}',
                f"keelgw_router_inference_seconds_sum {self.sum:.6f}",
                f"keelgw_router_inference_seconds_count {self.count}",
                "# HELP keelgw_router_head_info The loaded head; provisional heads are for trying the image only.",
                "# TYPE keelgw_router_head_info gauge",
                "keelgw_router_head_info{" + ",".join(f'{k}="{v}"' for k, v in sorted(self.info.items())) + "} 1",
            ]
        return "\n".join(out) + "\n"


class Router:
    def __init__(self, classify: Classify, info: dict[str, str], concurrency: int = 1, queue_ms: int = 1000):
        self.classify = classify
        self.info = info
        self.metrics = Metrics(info)
        self.slots = threading.BoundedSemaphore(concurrency)
        self.queue_s = queue_ms / 1000


def handler(router: Router, metrics_only: bool = False) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # Headers and body go out as two small writes. With Nagle's algorithm on,
        # the second waits for the client's delayed ACK: 40 ms on every request of
        # a kept-alive connection, which is every request from the gateway
        # (measured 2026-10-09: 49 ms against 9 ms for an 8 ms inference).
        disable_nagle_algorithm = True
        # A stalled or silent client gives up its thread after this long. It is
        # above the gateway's 90 s idle-connection timeout, so the Router never
        # closes a kept-alive connection the gateway is about to reuse.
        timeout = 120
        server_version = "keelgw-router"
        sys_version = ""

        def log_message(self, format, *args):  # noqa: A002
            pass  # no access log: the metrics count requests

        def send(self, code: int, body: dict | str, content_type: str = "application/json") -> None:
            data = (body if isinstance(body, str) else json.dumps(body)).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/metrics":
                return self.send(200, router.metrics.render(), "text/plain; version=0.0.4")
            if self.path in ("/healthz", "/readyz") and not metrics_only:
                return self.send(200, {"status": "ok", **router.info})
            self.send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if metrics_only or self.path != "/v1/classify":
                # The body is left unread, so it can't stay on the connection.
                self.close_connection = True
                return self.send(404, {"error": "not found"})
            code, body = self.classify()
            router.metrics.request(code)
            self.send(code, body)

        def body(self) -> bytes | None:
            """The request body, or None past MAX_BODY. Chunked bodies too:
            the Kubernetes API server's service proxy sends them."""
            if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
                out = b""
                while True:
                    size = int(self.rfile.readline(64).split(b";")[0].strip() or b"0", 16)
                    if size == 0:
                        while self.rfile.readline(1024).strip():  # trailers
                            pass
                        return out
                    if len(out) + size > MAX_BODY:
                        return None
                    out += self.rfile.read(size)
                    self.rfile.readline(8)  # the chunk's CRLF
            n = int(self.headers.get("Content-Length") or "0")
            if n < 0:
                raise ValueError("negative Content-Length")
            return None if n > MAX_BODY else self.rfile.read(n)

        def classify(self) -> tuple[int, dict]:
            try:
                raw = self.body()
            except ValueError:
                self.close_connection = True
                return 400, {"error": "unreadable body"}
            if raw is None:
                self.close_connection = True
                return 413, {"error": f"body over {MAX_BODY} bytes"}
            try:
                req = json.loads(raw)
                # Only the latest turn is classified (classifier.prepare says why);
                # any other field, such as an older gateway's "context", is ignored.
                text = req["text"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                return 400, {"error": 'want {"text": "<non-empty string>"}'}
            if not router.slots.acquire(timeout=router.queue_s):
                return 503, {"error": "busy"}
            try:
                t0 = time.perf_counter()
                probs = router.classify(text)
                took = time.perf_counter() - t0
                if len(probs) != len(c.TIERS):
                    raise ValueError(f"{len(probs)} scores for {len(c.TIERS)} Tiers")
            except Exception as e:  # noqa: BLE001 — the gateway falls back; never echo the prompt
                print(f"router: classify failed: {type(e).__name__}", file=sys.stderr, flush=True)
                return 500, {"error": "classification failed"}
            finally:
                router.slots.release()
            best = max(range(len(c.TIERS)), key=lambda i: probs[i])
            router.metrics.classified(c.TIERS[best], took)
            return 200, {
                "tier": c.TIERS[best],
                "scores": {t: round(float(p), 4) for t, p in zip(c.TIERS, probs, strict=True)},
                "latency_ms": round(took * 1000, 1),
            }

    return Handler


def load() -> tuple[Classify, dict[str, str]]:
    model_dir = Path(os.environ.get("ROUTER_MODEL_DIR", str(c.CACHE / "model")))
    head = c.Head.load(Path(os.environ.get("ROUTER_HEAD", str(c.HEAD))))
    emb = c.Embedder(model_dir, threads=int(os.environ.get("ROUTER_THREADS", "2")))

    def classify(text: str) -> list[float]:
        return head.probs(emb.embed([text]))[0].tolist()

    classify("warm up the session")
    info = {
        "model": c.MODEL_REPO,
        "model_revision": c.MODEL_REVISION,
        "provisional": str(bool(head.meta.get("provisional"))).lower(),
        "trained_at": str(head.meta.get("trained_at", "")),
    }
    return classify, info


def serve(router: Router, port: int, metrics_port: int = 0) -> list[ThreadingHTTPServer]:
    servers = [ThreadingHTTPServer(("", port), handler(router))]
    if metrics_port and metrics_port != port:
        servers.append(ThreadingHTTPServer(("", metrics_port), handler(router, metrics_only=True)))
    for s in servers:
        s.daemon_threads = True
        threading.Thread(target=s.serve_forever, daemon=True).start()
    return servers


def main() -> None:
    classify, info = load()
    if info["provisional"] == "true":
        print("router: WARNING: provisional head (train.py --from-generated); not for real traffic", file=sys.stderr)
    router = Router(
        classify, info, int(os.environ.get("ROUTER_CONCURRENCY", "1")), int(os.environ.get("ROUTER_QUEUE_MS", "1000"))
    )
    port = int(os.environ.get("PORT", "8080"))
    servers = serve(router, port, int(os.environ.get("ROUTER_METRICS_PORT", "0")))
    print(f"router: listening on :{port}, model {c.MODEL_REPO}@{c.MODEL_REVISION[:7]}", file=sys.stderr, flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
    for s in servers:
        s.shutdown()


if __name__ == "__main__":
    main()

"""The real API calls: for a simple and a complex prompt, the router and Claude agree.

These are the only tests that cost money: one Messages API request per prompt,
two in all, a fraction of a cent. They run only with `make test-live`, which
sets KEELGW_ROUTER_LIVE=1:

- without KEELGW_ROUTER_LIVE=1 they are skipped, whatever keys are set;
- with it but no ANTHROPIC_API_KEY or ANTHROPIC_API_KEY_FILE they fail, so a
  misconfigured run is visible rather than silently skipped;
- the default pytest run excludes the `live` marker as well.

Why Claude is in the test: the head learned its Tiers from Claude's labels, so
Claude is the reference the router imitates. Each test asks Claude to label the
prompt now, with dataset.py's own labelling request (the same system prompt,
Tier policies and JSON schema, through the standard Messages API instead of a
batch), and checks the router gives the same Tier. The key is read by the
Anthropic client from the environment and never printed.

It is also the verbose walkthrough. The same flag starts the router with
ROUTER_TRACE=1, so the request asks for a trace and the test prints each step
of the diagram (images/router.en.svg): admit, prepare, embed, decide, answer,
then the cross-check against Claude.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

import pytest

from keelgw_router import dataset as d

pytestmark = pytest.mark.live

# Standard (not batch) prices per million tokens for d.LABEL_MODEL.
PRICE_IN, PRICE_OUT = 1.0, 5.0


def say(line: str = "") -> None:
    print(line, flush=True)


def step(tag: str, title: str, *lines: str) -> None:
    say(f"\n{tag} {title}")
    for line in lines:
        say(f"     {line}")


def walk_router(url: str, body: bytes, out: dict, wall_ms: float) -> None:
    """Prints the router's trace, one diagram step at a time."""
    step("[caller]", "Gateway or client → HTTP server",
         f"POST {url}/v1/classify: a JSON body of {len(body)} bytes, with \"trace\": true")  # fmt: skip
    tr = out.get("trace")
    if tr is None:
        say("     (no trace came back: this router wasn't started with ROUTER_TRACE=1; `make test-live` does that)")
        return
    a, p, e, h = tr["admit"], tr["prepare"], tr["embed"], tr["decide"]
    step("[1 admit]", "HTTP server: one slot per process",
         f"read {a['body_bytes']} bytes, got the slot after {a['wait_ms']} ms "
         f"({a['concurrency']} slot, {a['queue_ms']} ms queue)",
         "with no slot in time it would answer 503 busy, and the caller would fall back")  # fmt: skip
    cap = "over the cap: first quarter and last three quarters kept" if p["chars_capped"] else "under the cap"
    if p["truncated"]:
        cut = (f"over the room of {p['room']}: kept the first 96 and the last {p['room'] - 96}, "
               f"dropped {p['dropped_tokens']} from the middle")  # fmt: skip
    else:
        cut = f"fits the room of {p['room']}, nothing dropped"
    step("[2 prepare]", "Tokenise + truncate",
         f"{p['chars']} characters, {cap} of 16,000",
         f"tokenised in {p['tokenise_ms']} ms: {' '.join(p['pieces'])}",
         f"{p['turn_tokens']} tokens, {cut}",
         f"model input = <s> + {p['prefix']!r} ({p['prefix_tokens']} tokens) + the prompt + </s> "
         f"= {p['model_tokens']} of {p['max_tokens']} token IDs")  # fmt: skip
    step("[3 embed]", f"{e['model']}, ONNX Runtime, CPU",
         f"{e['layers']} transformer layers over {e['hidden'][0]} tokens → {e['hidden'][0]} × {e['hidden'][1]} hidden states",
         f"mean pool over the tokens, then L2 normalise → {e['dim']} numbers (norm {e['norm']}), "
         f"starting {e['first']}",
         f"{e['ms']} ms: almost all of the router's time")  # fmt: skip
    ranked = sorted(out["scores"].items(), key=lambda kv: -kv[1])
    step("[4 decide]", "Logistic head: softmax(Wx + b)",
         f"W is {h['weights'][0]} × {h['weights'][1]}: {h['parameters']:,} trained numbers in model/head.json",
         "logits:  " + ", ".join(f"{t} {z:+.3f}" for t, z in h["logits"].items()),
         "softmax: " + ", ".join(f"{t} {s:.4f}" for t, s in ranked),
         f"argmax → {out['tier']} (margin {ranked[0][1] - ranked[1][1]:.4f} over {ranked[1][0]}), {h['ms']} ms")  # fmt: skip
    step("[5 answer]", "Tier + scores, JSON response",
         f"200 {{\"tier\": \"{out['tier']}\", \"scores\": ...}}: {out['latency_ms']} ms inside the router, "
         f"{wall_ms:.1f} ms over HTTP")  # fmt: skip


@pytest.mark.parametrize("tier", ["simple", "complex"])
def test_claude_and_the_router_agree_on_a_clear_cut_prompt(tier, prompts, request):
    if os.environ.get("KEELGW_ROUTER_LIVE") != "1":
        pytest.skip("makes a real API call: run `make test-live` (sets KEELGW_ROUTER_LIVE=1)")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY_FILE")):
        pytest.fail("KEELGW_ROUTER_LIVE=1 but neither ANTHROPIC_API_KEY nor ANTHROPIC_API_KEY_FILE is set")

    # Only now is the router needed: a skipped run shouldn't wait for it.
    router_url = request.getfixturevalue("router_url")
    p = next(x for x in prompts["live"] if x["tier"] == tier)
    say(f"\n\n=== keelgw-router live run: a {tier} prompt (diagram: images/router.en.svg) ===")
    say(f"prompt {p['id']} from tests/prompts.json, expected {p['tier']!r}:")
    say(f"     {p['text']!r}")

    body = json.dumps({"text": p["text"], "trace": True}).encode()
    req = urllib.request.Request(router_url + "/v1/classify", data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as r:
        out = json.loads(r.read())
    walk_router(router_url, body, out, (time.perf_counter() - t0) * 1000)
    router_tier = out["tier"]

    params = d.labelling_params([{"id": p["id"], "text": p["text"]}])
    params["model"] = os.environ.get("LIVE_LABEL_MODEL", d.LABEL_MODEL)
    step("[cross-check]", "Claude labels the same prompt: a real API call",
         f"the router's head was trained on labels from {d.LABEL_MODEL}, so it is the reference to agree with",
         f"{params['model']} gets dataset.py's labelling request: same system prompt, Tier policies, JSON schema")  # fmt: skip
    t0 = time.perf_counter()
    message = d.client().messages.create(**params)  # this test's one real call
    took = time.perf_counter() - t0
    labels = d.parse_labels(d.message_text(message), {p["id"]})
    got = labels.get(p["id"], {})
    usage = message.usage
    price = ""
    if params["model"] == d.LABEL_MODEL:
        price = f", about ${d.cost(usage.input_tokens, usage.output_tokens, (PRICE_IN, PRICE_OUT)):.4f}"
    say(f"     → {got.get('tier')!r} (confident: {got.get('confident')}) in {took:.1f} s, "
        f"{usage.input_tokens} input and {usage.output_tokens} output tokens{price}")  # fmt: skip

    agree = got.get("tier") == router_tier == p["tier"]
    say(f"\n[verdict] Claude {got.get('tier')!r}, router {router_tier!r}, expected {p['tier']!r}: "
        f"{'all three agree' if agree else 'MISMATCH'}\n")  # fmt: skip
    assert p["id"] in labels, f"the reply didn't label the prompt: stop_reason={message.stop_reason}"
    assert labels[p["id"]]["tier"] == p["tier"], labels[p["id"]]
    assert router_tier == p["tier"]

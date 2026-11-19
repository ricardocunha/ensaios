"""The single real API call: Claude labels one prompt, and the router agrees.

This is the one test that costs money (one Messages API request, a fraction of
a cent). It runs only with `make test-live`, which sets KEELGW_ROUTER_LIVE=1:

- without KEELGW_ROUTER_LIVE=1 it is skipped, whatever keys are set;
- with it but no ANTHROPIC_API_KEY or ANTHROPIC_API_KEY_FILE it fails, so a
  misconfigured run is visible rather than silently skipped;
- the default pytest run excludes the `live` marker as well.

It labels the prompt with dataset.py's own labelling request (the same system
prompt, Tier policies and JSON schema that labelled the training data), but
through the standard Messages API instead of a batch. The key is read by the
Anthropic client from the environment and never printed.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

from keelgw_router import dataset as d

pytestmark = pytest.mark.live


def test_claude_and_the_router_agree_on_a_clear_cut_prompt(prompts, request):
    if os.environ.get("KEELGW_ROUTER_LIVE") != "1":
        pytest.skip("makes a real API call: run `make test-live` (sets KEELGW_ROUTER_LIVE=1)")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY_FILE")):
        pytest.fail("KEELGW_ROUTER_LIVE=1 but neither ANTHROPIC_API_KEY nor ANTHROPIC_API_KEY_FILE is set")

    # Only now is the router needed: a skipped run shouldn't wait for it.
    router_url = request.getfixturevalue("router_url")
    p = prompts["live"]
    req = urllib.request.Request(router_url + "/v1/classify", data=json.dumps({"text": p["text"]}).encode(),
                                 headers={"Content-Type": "application/json"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=10) as r:
        router_tier = json.loads(r.read())["tier"]

    params = d.labelling_params([{"id": p["id"], "text": p["text"]}])
    params["model"] = os.environ.get("LIVE_LABEL_MODEL", d.LABEL_MODEL)
    message = d.client().messages.create(**params)  # the one real call
    labels = d.parse_labels(d.message_text(message), {p["id"]})

    print(f"\nlive: {params['model']} said {labels.get(p['id'], {}).get('tier')!r}, the router said {router_tier!r}; "
          f"{message.usage.input_tokens} input and {message.usage.output_tokens} output tokens")  # fmt: skip
    assert p["id"] in labels, f"the reply didn't label the prompt: stop_reason={message.stop_reason}"
    assert labels[p["id"]]["tier"] == p["tier"], labels[p["id"]]
    assert router_tier == p["tier"]

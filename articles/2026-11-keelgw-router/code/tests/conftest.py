"""Shared fixtures: the asserted prompts, and the router's URLs for e2e and live."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PROMPTS = json.loads((Path(__file__).parent / "prompts.json").read_text())


@pytest.fixture(scope="session")
def prompts() -> dict:
    return PROMPTS


def wait_healthy(base: str, timeout: float = 120) -> dict:
    """Polls GET /healthz until the router answers 200, or fails the test."""
    deadline, last = time.monotonic() + timeout, ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=5) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = str(e)
        time.sleep(1)
    pytest.fail(f"the router at {base} isn't healthy after {timeout:.0f} s ({last}); start it with `make up`")


@pytest.fixture(scope="session")
def router_url() -> str:
    base = os.environ.get("ROUTER_URL", f"http://localhost:{os.environ.get('ROUTER_HOST_PORT', '18080')}").rstrip("/")
    wait_healthy(base)
    return base


@pytest.fixture(scope="session")
def tight_url() -> str:
    base = os.environ.get("ROUTER_TIGHT_URL", f"http://localhost:{os.environ.get('ROUTER_TIGHT_HOST_PORT', '18081')}").rstrip("/")
    wait_healthy(base)
    return base

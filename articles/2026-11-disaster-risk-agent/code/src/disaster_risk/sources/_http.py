"""Tiny cached HTTP GET on top of the standard library.

Every download lands in ``code/data/<source>/`` (git-ignored). A file that is
already there is reused, so re-running is free and offline-friendly.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

# Some Brazilian government servers (INMET) reset connections that use the
# default Python/curl user agent, so we send a browser-like one.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

DATA_DIR = Path(os.environ.get("DISASTER_RISK_DATA", Path(__file__).resolve().parents[3] / "data"))


class BlockedError(RuntimeError):
    """The server refused an automated download (WAF page, captcha, auth)."""


def looks_like_waf_rejection(body: bytes) -> bool:
    """F5/BIG-IP style 'Request Rejected' page served with HTTP 200."""
    head = body[:600].lower()
    return b"<title>request rejected</title>" in head


def fetch(url: str, dest: Path, *, timeout: float = 600, force: bool = False) -> Path:
    """Download ``url`` to ``dest`` unless it already exists. Returns ``dest``."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as fh:
        first = resp.read(4096)
        if looks_like_waf_rejection(first):
            fh.close()
            tmp.unlink(missing_ok=True)
            raise BlockedError(f"server rejected automated download: {url}")
        fh.write(first)
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    tmp.rename(dest)
    return dest

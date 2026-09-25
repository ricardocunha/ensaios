"""Fetch an open font (DejaVu, free license) once and cache it, so rendering is identical on every machine."""

from __future__ import annotations

import urllib.request
from functools import cache
from pathlib import Path

from PIL import ImageFont

_CDN = "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/"
_CACHE = Path.home() / ".cache" / "cnh-ocr" / "fonts"
FILES = {"regular": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf", "mono": "DejaVuSansMono.ttf"}


def _path(style: str) -> Path:
    path = _CACHE / FILES[style]
    if not path.exists():
        _CACHE.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_CDN + FILES[style], path)
    return path


@cache
def font(style: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_path(style)), size)

"""SGB/CPRM SACE: official hydrological alert bulletins for the Taquari basin.

The archive page ``https://www.sgb.gov.br/sace/boletins.php?idbacia=9`` lists every bulletin PDF. A
file name such as ``20240430_06-20240430 - 075404.pdf`` carries the nominal time of the data (30/04
06h) and the upload time (07:54:04), both local (UTC-3). The station table is read with ``pdftotext``
(poppler) when it is installed. Downloads use ``curl``: Python's own CA bundle rejects the SGB
certificate chain, the system trust store accepts it (TLS verification stays on).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ._http import DATA_DIR, USER_AGENT

BASE = "https://www.sgb.gov.br/sace/"
LISTING_URL = BASE + "boletins.php?idbacia=9"  # 9 = Taquari

_FILE_RE = re.compile(r"boletins/Taquari/(\d{8})_(\d{2})-(\d{8}) - (\d{6})\.pdf")
_STAMP_RE = re.compile(r"(\d{2}/\d{2}/\d{4}) (\d{2}:\d{2})")


@dataclass(frozen=True)
class Bulletin:
    nominal: datetime  # local time the data refers to (naive, UTC-3)
    uploaded: datetime  # local time the file was uploaded (naive, UTC-3)
    path: str  # path relative to BASE

    @property
    def url(self) -> str:
        return BASE + self.path.replace(" ", "%20")

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class StationRow:
    station: str  # name as printed ("Muçum", "Estrela", ...)
    municipality: str
    rain_24h_mm: float | None
    level_cm: float | None  # None when printed "-" (equipment down) or missing
    change_24h_cm: float | None
    flood_level_cm: float | None  # "Nível de Inundação"; None when "#" (not defined)
    note: str  # forecast text / date, verbatim


def parse_listing(html: str) -> list[Bulletin]:
    out = {}
    for m in _FILE_RE.finditer(html):
        day, hour, up_day, up_time = m.groups()
        b = Bulletin(
            nominal=datetime.strptime(f"{day}{hour}", "%Y%m%d%H"),
            uploaded=datetime.strptime(f"{up_day}{up_time}", "%Y%m%d%H%M%S"),
            path=m.group(0),
        )
        out[b.path] = b
    return sorted(out.values(), key=lambda b: (b.nominal, b.uploaded))


def _num(tok: str) -> float | None:
    tok = tok.strip()
    if not tok or tok in {"-", "#"} or not re.fullmatch(r"[+-]?\d+(,\d+)?\*?", tok):
        return None
    return float(tok.rstrip("*").replace(",", "."))


def parse_bulletin_text(text: str) -> tuple[datetime | None, list[StationRow]]:
    """Parse ``pdftotext -layout`` output: the data timestamp and the station table."""
    stamp = None
    rows = []
    for line in text.splitlines():
        if stamp is None:
            m = _STAMP_RE.search(line)
            if m and "Porto Alegre" not in line:
                stamp = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d/%m/%Y %H:%M")
        toks = re.split(r"\s{2,}", line.strip())
        # Station rows with a river: name, river, municipality, rain, level, change, flood level, ...
        if len(toks) >= 6 and toks[1].startswith("Rio "):
            vals = toks[3:]
            rows.append(
                StationRow(
                    station=toks[0],
                    municipality=toks[2],
                    rain_24h_mm=_num(vals[0]),
                    level_cm=_num(vals[1]) if len(vals) > 1 else None,
                    change_24h_cm=_num(vals[2]) if len(vals) > 2 else None,
                    flood_level_cm=_num(vals[3]) if len(vals) > 3 else None,
                    note=" ".join(vals[4:]),
                )
            )
    return stamp, rows


def curl_fetch(url: str, dest: Path, *, timeout: int = 120) -> Path:
    """Cached download with the system ``curl`` (see module docstring)."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(
        ["curl", "-sSfL", "-m", str(timeout), "-A", USER_AGENT, "-o", str(tmp), url], check=True, timeout=timeout + 10
    )
    tmp.rename(dest)
    return dest


def download_listing(data_dir: Path = DATA_DIR) -> Path:
    return curl_fetch(LISTING_URL, data_dir / "sgb_sace" / "boletins_taquari.html")


def list_bulletins(data_dir: Path = DATA_DIR) -> list[Bulletin]:
    return parse_listing(download_listing(data_dir).read_bytes().decode("latin-1"))


def download_bulletin(b: Bulletin, data_dir: Path = DATA_DIR) -> Path:
    return curl_fetch(b.url, data_dir / "sgb_sace" / b.filename)


def pdf_text(pdf: Path) -> str | None:
    """Text of a bulletin PDF via ``pdftotext -layout`` (cached next to it), or None."""
    txt = pdf.with_suffix(".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8")
    exe = shutil.which("pdftotext")
    if exe is None:
        return None
    subprocess.run([exe, "-layout", str(pdf), str(txt)], check=True, timeout=60)
    return txt.read_text(encoding="utf-8")

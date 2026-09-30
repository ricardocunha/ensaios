"""Download a subset of the CARE to Compare dataset (Zenodo 15846963).

The full archive is one 5.5 GB zip. Zenodo serves it with HTTP range support,
so we read the zip's central directory remotely and pull only the members we
need (by default Wind Farm A, ~158 MB compressed / ~803 MB extracted).

    uv run python -m maintenance_agents.download            # Wind Farm A
    uv run python -m maintenance_agents.download --farms A B
    uv run python -m maintenance_agents.download --metadata-only

Wind Farm A also pulls the two EDP failure logbooks (2016, 2017), which carry
the component-level fault records that CARE's event_info only partly covers.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

RECORD_ID = "15846963"
ZIP_URL = f"https://zenodo.org/api/records/{RECORD_ID}/files/CARE_To_Compare.zip/content"
ZIP_SIZE = 5_503_439_673  # bytes, from the Zenodo record metadata
ZIP_MD5 = "2547b58c21ac8c242d13232860cf500c"  # of the whole archive (not checked: we never fetch it all)
ROOT = "CARE_To_Compare/"
FARMS = ("A", "B", "C")
METADATA_FILES = ("event_info.csv", "feature_description.csv")

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DATA_DIR = DATA_ROOT / "care"
EDP_DIR = DATA_ROOT / "edp"

# EDP Open Data failure logbooks for the wind farm behind CARE Wind Farm A
# (CC BY-SA 4.0, https://edp.com/en/innovation/data). Direct links, no login.
EDP_LOGBOOKS = {
    "failures-2016.xlsx": (
        "https://edp.com/sites/default/files/document/2025-04/Historical-Failure-Logbook-2016.xlsx",
        "271e73fa69144fa4d17d2acb0d8feae88841539d937328214c111b7b94d439cb",
    ),
    "failures-2017.xlsx": (
        "https://edp.com/sites/default/files/document/2025-04/opendata-wind-failures-2017.xlsx",
        "85aec8f9730874432539bffb7a370bc192e93dc901713d48e7b813c443247713",
    ),
}


class HttpRangeFile(io.RawIOBase):
    """Read-only, seekable file object backed by HTTP range requests."""

    def __init__(self, url: str, size: int | None = None, opener=urllib.request.urlopen):
        self.url = url
        self._open = opener
        self._pos = 0
        self.requests = 0
        self.size = size if size is not None else self._probe_size()

    def _probe_size(self) -> int:
        req = urllib.request.Request(self.url, headers={"Range": "bytes=0-0"})
        with self._open(req) as resp:
            content_range = resp.headers["Content-Range"]
        return int(content_range.rsplit("/", 1)[1])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            self._pos = self.size + offset
        else:
            raise ValueError(f"bad whence {whence}")
        return self._pos

    def readinto(self, buffer) -> int:
        if self._pos >= self.size or len(buffer) == 0:
            return 0
        end = min(self._pos + len(buffer), self.size) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self._pos}-{end}"})
        with self._open(req) as resp:
            data = resp.read()
        self.requests += 1
        n = len(data)
        buffer[:n] = data
        self._pos += n
        return n


def open_remote_zip(url: str = ZIP_URL, size: int | None = ZIP_SIZE) -> zipfile.ZipFile:
    raw = HttpRangeFile(url, size=size)
    return zipfile.ZipFile(io.BufferedReader(raw, buffer_size=4 << 20))


def select_members(names: list[str], farms: tuple[str, ...], metadata_only: bool) -> list[str]:
    """Pick the zip members for the given farms (plus README)."""
    wanted = [f"{ROOT}README.md"]
    for farm in farms:
        prefix = f"{ROOT}Wind Farm {farm}/"
        for name in names:
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            is_meta = name[len(prefix):] in METADATA_FILES
            if is_meta or (not metadata_only and name.startswith(prefix + "datasets/")):
                wanted.append(name)
    return sorted(set(n for n in wanted if n in names))


def download(
    farms: tuple[str, ...] = ("A",),
    data_dir: Path = DEFAULT_DATA_DIR,
    metadata_only: bool = False,
    zf: zipfile.ZipFile | None = None,
) -> list[Path]:
    for farm in farms:
        if farm not in FARMS:
            raise ValueError(f"unknown farm {farm!r}; expected one of {FARMS}")
    zf = zf or open_remote_zip()
    infos = {i.filename: i for i in zf.infolist()}
    members = select_members(list(infos), farms, metadata_only)
    total = sum(infos[m].compress_size for m in members)
    print(f"{len(members)} files, {total / 1e6:.0f} MB compressed -> {data_dir}", file=sys.stderr)
    written = []
    for name in members:
        target = data_dir / name[len(ROOT):]
        if target.exists() and target.stat().st_size == infos[name].file_size:
            written.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        with zf.open(name) as src, open(tmp, "wb") as dst:  # zipfile checks CRC-32 on read
            shutil.copyfileobj(src, dst, length=1 << 20)
        tmp.replace(target)
        print(f"  {target.relative_to(data_dir)} ({infos[name].file_size / 1e6:.1f} MB)", file=sys.stderr)
        written.append(target)
    return written


def download_edp_logbooks(edp_dir: Path = EDP_DIR, opener=urllib.request.urlopen) -> list[Path]:
    """Fetch the two EDP failure logbooks and check their SHA-256."""
    edp_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name, (url, sha256) in EDP_LOGBOOKS.items():
        target = edp_dir / name
        if not (target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256):
            req = urllib.request.Request(url, headers={"User-Agent": "maintenance-agents/0.1"})
            with opener(req) as resp:
                body = resp.read()
            digest = hashlib.sha256(body).hexdigest()
            if digest != sha256:
                raise RuntimeError(f"{name}: sha256 {digest} != expected {sha256}; the upstream file changed")
            target.write_bytes(body)
            print(f"  edp/{name} ({len(body) / 1e3:.0f} kB)", file=sys.stderr)
        out.append(target)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--farms", nargs="+", default=["A"], choices=FARMS)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--metadata-only", action="store_true", help="only event_info / feature_description")
    args = parser.parse_args(argv)
    download(tuple(args.farms), args.data_dir, args.metadata_only)
    if "A" in args.farms:
        download_edp_logbooks()


if __name__ == "__main__":
    main()

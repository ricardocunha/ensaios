import hashlib
import io
import zipfile

import pytest

from maintenance_agents import download as dl


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers: dict | None = None):
        super().__init__(body)
        self.headers = headers or {}


def range_opener(blob: bytes, log: list):
    """Serve `blob` like an HTTP server that honours Range headers."""

    def _open(req):
        rng = req.get_header("Range")
        log.append(rng)
        start, end = (int(x) for x in rng.removeprefix("bytes=").split("-"))
        return FakeResponse(blob[start : end + 1], {"Content-Range": f"bytes {start}-{end}/{len(blob)}"})

    return _open


def fake_care_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("CARE_To_Compare/", "")
        z.writestr("CARE_To_Compare/README.md", "readme")
        for farm in "ABC":
            z.writestr(f"CARE_To_Compare/Wind Farm {farm}/", "")
            z.writestr(f"CARE_To_Compare/Wind Farm {farm}/event_info.csv", f"events {farm}")
            z.writestr(f"CARE_To_Compare/Wind Farm {farm}/feature_description.csv", f"features {farm}")
            z.writestr(f"CARE_To_Compare/Wind Farm {farm}/datasets/", "")
            z.writestr(f"CARE_To_Compare/Wind Farm {farm}/datasets/1.csv", f"{farm};" * 5000)
    return buf.getvalue()


def test_http_range_file_reads_and_seeks():
    blob = bytes(range(256)) * 10
    log = []
    f = dl.HttpRangeFile("http://x", opener=range_opener(blob, log))
    assert f.size == len(blob)
    f.seek(-10, io.SEEK_END)
    assert f.read(10) == blob[-10:]
    f.seek(100)
    assert f.read(5) == blob[100:105]
    assert f.read(10_000) == blob[105:]
    assert f.read(1) == b""
    assert log[0] == "bytes=0-0"  # size probe


def test_select_members():
    names = [
        "CARE_To_Compare/README.md",
        "CARE_To_Compare/Wind Farm A/",
        "CARE_To_Compare/Wind Farm A/event_info.csv",
        "CARE_To_Compare/Wind Farm A/datasets/0.csv",
        "CARE_To_Compare/Wind Farm B/datasets/5.csv",
    ]
    assert dl.select_members(names, ("A",), metadata_only=False) == [
        "CARE_To_Compare/README.md",
        "CARE_To_Compare/Wind Farm A/datasets/0.csv",
        "CARE_To_Compare/Wind Farm A/event_info.csv",
    ]
    assert "CARE_To_Compare/Wind Farm A/datasets/0.csv" not in dl.select_members(names, ("A",), metadata_only=True)


def test_download_extracts_only_requested_farm(tmp_path):
    blob = fake_care_zip()
    log = []
    zf = zipfile.ZipFile(io.BufferedReader(dl.HttpRangeFile("http://x", opener=range_opener(blob, log))))
    paths = dl.download(("A",), tmp_path, zf=zf)
    rel = sorted(p.relative_to(tmp_path).as_posix() for p in paths)
    assert rel == ["README.md", "Wind Farm A/datasets/1.csv", "Wind Farm A/event_info.csv", "Wind Farm A/feature_description.csv"]
    assert (tmp_path / "Wind Farm A/datasets/1.csv").read_text() == "A;" * 5000
    assert not (tmp_path / "Wind Farm B").exists()
    # second run skips existing files (no new member reads)
    n = len(log)
    dl.download(("A",), tmp_path, zf=zf)
    assert len(log) == n


def test_download_rejects_unknown_farm(tmp_path):
    with pytest.raises(ValueError):
        dl.download(("Z",), tmp_path, zf=zipfile.ZipFile(io.BytesIO(fake_care_zip())))


def test_edp_logbooks_checksum(tmp_path, monkeypatch):
    body = b"xlsx bytes"
    monkeypatch.setattr(dl, "EDP_LOGBOOKS", {"failures-2017.xlsx": ("http://edp/x.xlsx", hashlib.sha256(body).hexdigest())})
    opener = lambda req: FakeResponse(body)  # noqa: E731
    [path] = dl.download_edp_logbooks(tmp_path, opener=opener)
    assert path.read_bytes() == body

    monkeypatch.setattr(dl, "EDP_LOGBOOKS", {"failures-2016.xlsx": ("http://edp/y.xlsx", "0" * 64)})
    with pytest.raises(RuntimeError, match="upstream file changed"):
        dl.download_edp_logbooks(tmp_path, opener=opener)

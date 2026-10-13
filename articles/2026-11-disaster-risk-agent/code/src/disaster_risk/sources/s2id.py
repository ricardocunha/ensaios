"""S2iD / Atlas Digital de Desastres: historical disaster records.

The consolidated file ("1991 a 2025 - Danos Informados", CC-BY) is listed by the MDR open-data CKAN
API, but on 2026-09-30 every ``/download/`` URL answered scripted requests with an F5 "Request
Rejected" page. If the download is rejected, save the CSV by hand from a browser at
``data/s2id/<resource file name>``.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ._http import DATA_DIR, USER_AGENT, BlockedError, fetch

PACKAGE_API = "https://dadosabertos.mdr.gov.br/api/3/action/package_show?id=s2id_sedec"


@dataclass(frozen=True)
class Resource:
    name: str
    format: str
    url: str
    last_modified: str | None

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def parse_package(pkg_json: dict) -> list[Resource]:
    return [
        Resource(r["name"], r.get("format", ""), r["url"], r.get("last_modified"))
        for r in pkg_json["result"]["resources"]
    ]


def list_resources() -> list[Resource]:
    req = urllib.request.Request(PACKAGE_API, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return parse_package(json.load(resp))


def history_resource(resources: list[Resource]) -> Resource:
    return next(r for r in resources if "Danos Informados" in r.name and r.format.upper() == "CSV" and "1991" in r.name)


def download_history(data_dir: Path = DATA_DIR) -> Path:
    res = history_resource(list_resources())
    dest = data_dir / "s2id" / res.filename
    try:
        return fetch(res.url, dest, timeout=900)
    except BlockedError as e:
        raise BlockedError(
            f"{e}. Download it in a browser from https://dadosabertos.mdr.gov.br/dataset/s2id_sedec "
            f"and save it as {dest}"
        ) from None

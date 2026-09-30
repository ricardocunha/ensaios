"""Copernicus EMS Rapid Mapping: precomputed flood extent for EMSR720.

The public dashboard API lists every AOI and product of an activation; each
product is a zip (shapefiles + GeoJSON + GeoTIFF + PDF map) that redirects to
a public S3 bucket. No key needed.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ._http import DATA_DIR, fetch

API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code={code}"


@dataclass(frozen=True)
class Product:
    activation: str
    aoi_number: int
    aoi_name: str
    kind: str  # DEL = delineation (flood extent), GRA = grading (damage)
    monitoring: int  # 0 = first product, 1.. = later monitoring updates
    sensor: str | None
    acquired: str | None  # ISO time of the image the product was made from
    download_url: str

    @property
    def filename(self) -> str:
        return self.download_url.rsplit("/", 1)[-1]


def download_activation(code: str, data_dir: Path = DATA_DIR) -> Path:
    return fetch(API.format(code=code), data_dir / "copernicus_ems" / f"{code}.json", timeout=120)


def parse_products(activation_json: dict) -> list[Product]:
    act = activation_json["results"][0]
    out = []
    for aoi in act["aois"]:
        for p in aoi.get("products", []):
            if not p.get("downloadPath"):
                continue  # e.g. a product that was not feasible / never delivered
            img = (p.get("images") or [{}])[0]
            out.append(
                Product(
                    activation=act["code"],
                    aoi_number=aoi["number"],
                    aoi_name=aoi["name"],
                    kind=p["type"],
                    monitoring=p.get("monitoringNumber", 0),
                    sensor=img.get("sensorName"),
                    acquired=img.get("acquisitionTime"),
                    download_url=p["downloadPath"],
                )
            )
    out.sort(key=lambda p: (p.aoi_number, p.kind, p.monitoring))
    return out


def list_products(code: str, data_dir: Path = DATA_DIR) -> list[Product]:
    return parse_products(json.loads(download_activation(code, data_dir).read_text()))


def download_product(product: Product, data_dir: Path = DATA_DIR) -> Path:
    return fetch(product.download_url, data_dir / "copernicus_ems" / product.filename)


def read_observed_event(zip_path: Path) -> dict:
    """Return the flood polygons (``observedEventA`` GeoJSON, CRS84) of a DEL product."""
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if "_observedEventA_" in n and n.endswith(".json"))
        return json.loads(z.read(name))

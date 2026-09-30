import json
import zipfile

from disaster_risk.sources import copernicus_ems as ems


def test_parse_products_skips_undelivered(fixtures):
    data = json.loads((fixtures / "ems_activation.json").read_text())
    products = ems.parse_products(data)
    assert all(p.download_url for p in products)
    dels = [p for p in products if p.kind == "DEL"]
    assert {p.aoi_name for p in dels} == {"Guapore", "Encantado"}
    first = products[0]
    assert first.activation == "EMSR720"
    assert first.filename.endswith(".zip")


def test_products_sorted_by_aoi_kind_monitoring(fixtures):
    products = ems.parse_products(json.loads((fixtures / "ems_activation.json").read_text()))
    keys = [(p.aoi_number, p.kind, p.monitoring) for p in products]
    assert keys == sorted(keys)


def test_read_observed_event(tmp_path):
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"notation": "Flooded area"}, "geometry": None}]}
    zpath = tmp_path / "p.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("EMSR720_AOI02_DEL_PRODUCT_observedEventA_v1.json", json.dumps(gj))
        z.writestr("EMSR720_AOI02_DEL_PRODUCT_floodDepthA_v1.json", "{}")
    assert ems.read_observed_event(zpath)["features"][0]["properties"]["notation"] == "Flooded area"

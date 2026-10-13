import json

from conftest import make_csv
from eye_rag.viewer import build, write


def _jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows))


def _vlm(image, labels, case_labels=(), **extra):
    cases = [f"train/{i + 1}" for i in range(len(case_labels))]
    return {"id": image, "labels": labels, "cited_cases": [1] if cases else [], "rationale": "r", "case_ids": cases, "case_labels": list(case_labels), **extra}


def _fixture(tmp_path):
    root, runs = tmp_path / "rfmid", tmp_path / "runs"
    root.mkdir()
    runs.mkdir()
    (root / "test_labels.csv").write_text(make_csv([(1, {"DR"}), (2, set()), (10, {"MH"})]), encoding="utf-8")
    _jsonl(runs / "m2_vlm_test_zero_shot.jsonl", [_vlm("test/1", ["MH"])])
    _jsonl(runs / "m2_vlm_test_retrieval.jsonl", [_vlm("test/10", ["MH"], [["MH"]]), _vlm("test/2", ["normal"], [["NORMAL"]]), _vlm("test/1", ["DR"], [["DR"]])])
    _jsonl(runs / "m2_vlm_test_shuffled.jsonl", [_vlm("test/1", ["ODC"], [["ODC"]], true_case_labels=[["DR"]])])
    explanation = {"id": "test/1", "findings": [{"label": "DR", "source": "both", "cases": [1], "reason": "x"}], "verified": True, "attempts": 1, "first_problems": [], "problems": [], "raw_last": "{}"}
    _jsonl(runs / "m2_explain_test_retrieval.jsonl", [explanation])
    return root, runs


def test_build_joins_the_arms_per_image(tmp_path):
    root, runs = _fixture(tmp_path)
    data = build(runs, "test", root)
    assert [c["id"] for c in data["cases"]] == ["test/1", "test/2", "test/10"]
    first, normal = data["cases"][0], data["cases"][1]
    assert first["truth"] == ["DR"] and first["image"] == "rfmid/test/1.jpg"
    assert set(first["arms"]) == {"zero_shot", "retrieval", "shuffled"}
    assert first["arms"]["retrieval"]["explanation"]["verified"] is True
    assert "raw_last" not in first["arms"]["retrieval"]["explanation"]
    assert first["arms"]["shuffled"]["cases"] == [{"id": "train/1", "image": "rfmid/train/1.jpg", "labels": ["ODC"], "true_labels": ["DR"]}]
    # a normal image and a NORMAL case use the diagnosis vocabulary
    assert normal["truth"] == ["normal"] and normal["arms"]["retrieval"]["cases"][0]["labels"] == ["normal"]
    assert set(normal["arms"]) == {"retrieval"}
    assert data["conditions"]["DR"]["name"] == "diabetic retinopathy" and "normal" in data["conditions"]
    assert data["summary"] == {}


def test_write_links_the_images_instead_of_copying(tmp_path):
    root, runs = _fixture(tmp_path)
    out = tmp_path / "public"
    for _ in range(2):  # a second run replaces the link
        path = write(build(runs, "test", root), out, root)
    assert json.loads(path.read_text())["split"] == "test"
    assert (out / "rfmid").is_symlink() and (out / "rfmid").resolve() == root.resolve()

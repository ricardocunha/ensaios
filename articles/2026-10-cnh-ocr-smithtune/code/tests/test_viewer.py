import json
from pathlib import Path

import pytest

from cnh_ocr import transcription as tx
from cnh_ocr.schema import CnhRecord
from cnh_ocr.viewer import build, write

RECORD = CnhRecord(nome="ANA LIMA", doc_identidade="1234567", orgao_emissor="SSP", uf_emissor="SP", cpf="529.982.247-25",
                   data_nascimento="01/02/1990", filiacao=["JOSE LIMA", "MARIA LIMA"], categoria="B", numero_registro="12345678901",
                   validade="01/02/2030", primeira_habilitacao="01/02/2010", local="SAO PAULO, SP", data_emissao="01/02/2020")
DECOY = "NOME: ANA LIMA\nNATURALIDADE: SANTOS"
RESULTS = """# Results

## BID (real CNH templates)

| Reader run | CNHs | label acc |
|---|---|---|
| bid-paddleocr_vl-lora-v3 | 70 | 81.0% |

## Extractor (Stage 2)

| Extractor run | n | exact records |
|---|---|---|
| student-tuned | 99 | 80.8% |
"""


def _jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def _meta(name, record=None):
    answer = tx.from_record(record) if record else DECOY
    return {"file_name": f"images/{name}.jpg", "answer": answer, "kind": "cnh" if record else "non_cnh",
            "record": record.model_dump_json() if record else "", "difficulty": "normal"}


def _fixture(tmp_path):
    data, runs = tmp_path / "data", tmp_path / "runs"
    _jsonl(data / "synth-v3/test/metadata.jsonl", [_meta("test-0", RECORD), _meta("test-1"), _meta("test-2", RECORD)])
    _jsonl(data / "bid/test/metadata.jsonl", [_meta("CNH_Frente-1_in", RECORD)])
    for split in ("synth-v3/test", "bid/test"):
        (data / split / "images").mkdir()
    read = tx.from_record(RECORD).replace("529.982.247-25", "529.982.247-26")
    _jsonl(runs / "reader/bid-paddleocr_vl-lora-v3.jsonl", [{"file_name": "images/CNH_Frente-1_in.jpg", "transcription": read, "seconds": 2.0}])
    _jsonl(runs / "reader/bid-paddleocr_vl-zeroshot.jsonl", [{"file_name": "images/CNH_Frente-1_in.jpg", "transcription": "NÃO É CNH", "seconds": 1.0}])
    scored = {"role": "student", "run_id": "t1", "field_accuracy": 1.0, "exact": True, "tool_calls": 1, "model": "m"}
    _jsonl(runs / "extractor/student-base.jsonl", [
        {**scored, "file_name": "images/test-1.jpg", "fields": {}, "outcome": {"motivo": "RG"}},
        {**scored, "file_name": "images/test-0.jpg", "run_id": "t0", "fields": {"nome": True}, "outcome": RECORD.model_dump()}])
    calls = [{"role": "human", "content": "x"},
             {"role": "ai", "content": [{"type": "text", "text": ""}, {"type": "tool_call", "id": "c1", "name": "reject_document", "args": {"motivo": "RG"}}]},
             {"role": "tool", "tool_call_id": "c1", "content": "REJECTED"}, {"role": "ai", "content": "OK"}]
    _jsonl(runs / "smithtune/golden/conversations/a.json", [{"trace_ids": ["t1"], "example": {"inputs": {"messages": calls}}}])
    (tmp_path / "RESULTS.md").write_text(RESULTS, encoding="utf-8")
    return data, runs


def test_build_follows_each_image_through_the_runs(tmp_path):
    data, runs = _fixture(tmp_path)
    built = build(data, runs, tmp_path / "RESULTS.md")
    assert [(s["key"], s["count"]) for s in built["sets"]] == [("student", 2), ("bid", 1)]
    cnh, decoy, bid = built["items"]
    assert cnh["id"] == "student/test-0" and cnh["image"] == "img/student/test-0.jpg"
    # the Extractor's input is rebuilt from the printed text; the expected record comes with it
    assert cnh["extractor"]["source"] == "noise" and cnh["extractor"]["expected"]["cpf"] == "529.982.247-25"
    assert cnh["extractor"]["runs"][0]["fields"] == {"nome": True} and "steps" not in cnh["extractor"]["runs"][0]
    assert decoy["extractor"]["input"] == DECOY and decoy["extractor"]["expected"] is None and not decoy["extractor"]["gate"]["is_cnh"]
    assert decoy["extractor"]["runs"][0]["steps"] == [{"turn": 1, "tool": "reject_document", "args": {"motivo": "RG"}, "result": "REJECTED"}]
    # zero-shot comes before the LoRA rounds; labels are compared with what is printed
    zero, tuned = bid["readers"]
    assert zero["name"] == "PaddleOCR-VL, zero-shot" and zero["refused"] and not zero["gate"]["is_cnh"]
    assert tuned["name"] == "PaddleOCR-VL, LoRA round 3" and tuned["gate"]["is_cnh"]
    assert [l["label"] for l in tuned["labels"] if not l["ok"]] == ["CPF"]
    assert built["summary"]["BID (real CNH templates)"]["bid-paddleocr_vl-lora-v3"] == {"CNHs": "70", "label acc": "81.0%"}
    assert built["summary"]["Extractor (Stage 2)"]["student-tuned"]["exact records"] == "80.8%"


def test_build_names_the_make_target_when_no_run_exists(tmp_path):
    with pytest.raises(FileNotFoundError, match="make zero-shot"):
        build(tmp_path / "data", tmp_path / "runs", tmp_path / "RESULTS.md")


def test_write_links_the_images_and_refuses_the_private_folder(tmp_path, monkeypatch):
    data, runs = _fixture(tmp_path)
    out = tmp_path / "public"
    for _ in range(2):  # a second run replaces the links
        path = write(build(data, runs, tmp_path / "RESULTS.md"), out, data)
    assert len(json.loads(path.read_text(encoding="utf-8"))["items"]) == 3
    assert (out / "img/bid").is_symlink() and (out / "img/bid").resolve() == (data / "bid/test/images").resolve()
    with pytest.raises(ValueError, match="private"):
        monkeypatch.chdir(tmp_path)
        build(Path("private/data"), runs)

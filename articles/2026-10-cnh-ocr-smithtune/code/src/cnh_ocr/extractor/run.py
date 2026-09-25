"""Run the Extractor over Transcriptions, trace to LangSmith, score against ground truth.

    # Teacher trajectories for smithtune (costs Anthropic API credits):
    uv run python -m cnh_ocr.extractor.run --role teacher --data data/synth/train --limit 1500 \
        --project cnh-extractor-teacher
    # Same inputs through the deployed Student:
    uv run python -m cnh_ocr.extractor.run --role student --student-url $STUDENT_URL \
        --student-model $STUDENT_MODEL --data data/synth/test --project cnh-extractor-student

Inputs are ground-truth Transcriptions with injected OCR noise, or real Reader
output via `--transcriptions runs/reader/<model>.jsonl`. Each run gets LangSmith
feedback (`field_accuracy`, `exact`), which is the signal smithtune triage uses.
"""

from __future__ import annotations

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langchain_core.tracers.context import collect_runs
from langsmith import Client

from ..evaluation.metrics import score_record
from ..schema import CnhRecord
from .agent import build_extractor, final_outcome, outcome_json, student_model, teacher_model, user_message
from .noise import add_noise


def load_inputs(data: Path, transcriptions: Path | None, limit: int | None, seed: int) -> list[dict]:
    rows = [json.loads(line) for line in (data / "metadata.jsonl").open(encoding="utf-8")]
    reader_out = {}
    if transcriptions:
        reader_out = {r["file_name"]: r["transcription"]
                      for r in map(json.loads, transcriptions.open(encoding="utf-8"))}
    rng = random.Random(seed)
    items = []
    for row in rows[:limit]:
        if row["file_name"] in reader_out:
            text, source = reader_out[row["file_name"]], "reader"
        elif row["kind"] == "non_cnh":
            text, source = row["answer"], "clean"
            # A Reader sometimes transcribes a non-CNH instead of refusing; teach the Extractor to catch it.
            if rng.random() < 0.5:
                text, source = "NOME: FULANO DE TAL\nREGISTRO GERAL: 12.345.678-9\nNATURALIDADE: SALVADOR", "decoy"
        else:
            text, source = add_noise(row["answer"], rng), "noise"
        truth = CnhRecord.model_validate_json(row["record"]) if row["record"] else None
        items.append({"file_name": row["file_name"], "transcription": text, "source": source, "truth": truth})
    return items


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--role", choices=("teacher", "student"), required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--transcriptions", type=Path)
    p.add_argument("--limit", type=int)
    p.add_argument("--project", required=True, help="LangSmith project to trace into")
    p.add_argument("--student-url")
    p.add_argument("--student-model")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    import os
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = args.project

    model = teacher_model() if args.role == "teacher" else student_model(args.student_url, args.student_model)
    agent = build_extractor(model)
    client = Client()
    items = load_inputs(args.data, args.transcriptions, args.limit, args.seed)

    def run_one(item: dict) -> dict:
        meta = {"file_name": item["file_name"], "input_source": item["source"], "role": args.role}
        with collect_runs() as cb:
            result = agent.invoke({"messages": [user_message(item["transcription"])]},
                                  config={"metadata": meta, "tags": [args.role, item["source"]]})
        outcome = final_outcome(result["messages"])
        score = score_record(outcome, item["truth"])
        run_id = cb.traced_runs[0].id if cb.traced_runs else None
        if run_id:
            client.create_feedback(run_id, key="field_accuracy", score=score.field_accuracy)
            client.create_feedback(run_id, key="exact", score=int(score.exact))
        return {**meta, "run_id": str(run_id), "field_accuracy": score.field_accuracy, "exact": score.exact,
                "fields": score.fields, "outcome": json.loads(outcome_json(outcome)),
                "tool_calls": sum(len(getattr(m, "tool_calls", []) or []) for m in result["messages"])}

    out = args.out or Path("runs/extractor") / f"{args.project}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    with out.open("w", encoding="utf-8") as f, ThreadPoolExecutor(args.concurrency) as pool:
        for row in pool.map(run_one, items):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            done += 1
            print(f"[{done}/{len(items)}] {row['file_name']} acc={row['field_accuracy']:.2f} "
                  f"exact={row['exact']} calls={row['tool_calls']}")
    client.flush()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

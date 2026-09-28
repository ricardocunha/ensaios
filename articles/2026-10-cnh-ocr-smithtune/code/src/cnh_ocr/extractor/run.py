"""Run the Extractor over Transcriptions, trace to LangSmith, score against ground truth.

    # Teacher trajectories for smithtune (costs Anthropic API credits):
    uv run python -m cnh_ocr.extractor.run --role teacher --data data/synth-v3/train --limit 1500
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
import os
import random
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from langchain_core.tracers.context import collect_runs
from langsmith import Client

from .. import transcription as tx
from ..evaluation.metrics import score_record
from ..schema import CnhRecord
from .agent import build_extractor, final_outcome, outcome_json, student_model, teacher_model, user_message
from .noise import add_noise


def usage(messages) -> dict:
    """Token usage summed over the run's model calls (for measured cost, not estimates)."""
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_read": 0, "cache_creation": 0, "model_calls": 0}
    for m in messages:
        meta = getattr(m, "usage_metadata", None)
        if meta:
            details = meta.get("input_token_details") or {}
            totals["input_tokens"] += meta.get("input_tokens", 0)  # includes cached tokens
            totals["output_tokens"] += meta.get("output_tokens", 0)
            totals["cache_read"] += details.get("cache_read", 0) or 0
            # langchain-anthropic reports writes per TTL (ephemeral_5m/1h) and then zeroes the
            # generic key, so sum all three.
            totals["cache_creation"] += sum(details.get(k, 0) or 0 for k in
                                            ("cache_creation", "ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"))
            totals["model_calls"] += 1
    return totals


# List prices, US$ per million tokens. Claude: Anthropic pricing (cache reads 0.1x, 5-minute writes
# 1.25x). Baseten models: from GET https://inference.baseten.co/v1/models (2026-09-28). The real
# bill is in each provider's console.
PRICES = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "deepseek-ai/DeepSeek-V4-Pro-0813": {"input": 1.32, "output": 3.96, "cache_read": 0.132, "cache_write": 1.32},
    "openai/gpt-oss-120b": {"input": 0.10, "output": 0.50, "cache_read": 0.10, "cache_write": 0.10},
}


def run_cost(u: dict, model: str | None = None) -> float:
    price = PRICES[model or u.get("model") or os.getenv("TEACHER_MODEL", "claude-sonnet-5")]
    uncached = u["input_tokens"] - u.get("cache_read", 0) - u.get("cache_creation", 0)
    return (uncached * price["input"] + u.get("cache_read", 0) * price["cache_read"]
            + u.get("cache_creation", 0) * price["cache_write"] + u["output_tokens"] * price["output"]) / 1e6


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
            # v3 data (ADR-0003): the Reader transcribes decoys, so the Extractor sees what an RG,
            # CPF card or invoice actually prints and must reject it. v1/v2 data only has a refusal.
            text, source = (row["answer"], "decoy") if row["answer"] != tx.NOT_A_CNH else (row["answer"], "refusal")
        else:
            dropped: list[str] = []
            text, source = add_noise(row["answer"], rng, dropped=dropped), "noise"
        truth = CnhRecord.model_validate_json(row["record"]) if row["record"] else None
        if truth is not None and source == "noise" and dropped:
            # The Extractor can't know a value whose line never reached it: expect null there.
            truth = truth.model_copy(update={f: None for label in dropped for f in tx.LABEL_FIELDS[label]})
        items.append({"file_name": row["file_name"], "transcription": text, "source": source, "truth": truth})
    return items


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--role", choices=("teacher", "student"), required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--transcriptions", type=Path)
    p.add_argument("--limit", type=int)
    p.add_argument("--project", help="LangSmith project to trace into (default: LANGSMITH_PROJECT from .env)")
    p.add_argument("--student-url")
    p.add_argument("--student-model")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--max-cost", type=float, help="stop starting new runs once measured spend reaches this (US$)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path)
    load_dotenv(find_dotenv(usecwd=True))  # ANTHROPIC_API_KEY, LANGSMITH_* from code/.env
    args = p.parse_args()
    args.project = args.project or os.environ.get("LANGSMITH_PROJECT")
    if not args.project:
        p.error("--project or LANGSMITH_PROJECT (in .env) is required")
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = args.project

    model = teacher_model() if args.role == "teacher" else student_model(args.student_url, args.student_model)
    agent = build_extractor(model)
    client = Client()
    items = load_inputs(args.data, args.transcriptions, args.limit, args.seed)

    def run_one(item: dict) -> dict:
        meta = {"file_name": item["file_name"], "input_source": item["source"], "role": args.role}
        with collect_runs() as cb:
            # recursion_limit: a model stuck retrying a failing tool call becomes a failed run
            # (excluded) instead of looping for minutes.
            result = agent.invoke({"messages": [user_message(item["transcription"])]},
                                  config={"metadata": meta, "tags": [args.role, item["source"]],
                                          "recursion_limit": 40})
        outcome = final_outcome(result["messages"])
        score = score_record(outcome, item["truth"])
        run_id = cb.traced_runs[0].id if cb.traced_runs else None
        if run_id:
            client.create_feedback(run_id, key="field_accuracy", score=score.field_accuracy)
            client.create_feedback(run_id, key="exact", score=int(score.exact))
        return {**meta, "run_id": str(run_id), "field_accuracy": score.field_accuracy, "exact": score.exact,
                "fields": score.fields, "outcome": json.loads(outcome_json(outcome)),
                "tool_calls": sum(len(getattr(m, "tool_calls", []) or []) for m in result["messages"]),
                "model": getattr(model, "model", None) or getattr(model, "model_name", None),
                **usage(result["messages"])}

    out = args.out or Path("runs/extractor") / f"{args.project}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done, failed, spent, stop_reason = 0, 0, 0.0, None
    queue = iter(items)
    with out.open("w", encoding="utf-8") as f, ThreadPoolExecutor(args.concurrency) as pool:
        running = set()

        def refill():
            # Start new runs only while under budget; in-flight runs are always allowed to finish.
            while stop_reason is None and len(running) < args.concurrency:
                if args.max_cost is not None and spent >= args.max_cost:
                    return
                item = next(queue, None)
                if item is None:
                    return
                running.add(pool.submit(run_one, item))

        refill()
        while running:
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for fut in finished:
                running.remove(fut)
                try:
                    row = fut.result()
                except Exception as e:  # one failed run must not lose the others
                    failed += 1
                    msg = f"{type(e).__name__}: {e}"
                    print(f"[error] {msg[:200]}")
                    if "credit balance" in msg.lower() or "billing" in msg.lower():
                        stop_reason = "Anthropic credit/billing error"
                    continue
                spent += run_cost(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                done += 1
                print(f"[{done}/{len(items)}] {row['file_name']} acc={row['field_accuracy']:.2f} "
                      f"exact={row['exact']} calls={row['tool_calls']} spent=${spent:.2f}")
            refill()
    if stop_reason is None and args.max_cost is not None and spent >= args.max_cost:
        stop_reason = f"budget reached (${spent:.2f} >= ${args.max_cost:.2f})"
    client.flush()
    print(f"wrote {out}: {done} runs, {failed} failed, measured spend ${spent:.2f}"
          + (f"; stopped early: {stop_reason}" if stop_reason else ""))


if __name__ == "__main__":
    main()

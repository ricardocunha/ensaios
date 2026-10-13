"""Turn smithtune's prepared splits into mlx-lm chat SFT data for a local Student.

    uv run python -m cnh_ocr.student.build_sft --prepared runs/smithtune/golden/prepared --out data/student-sft

Plan B (see docs/SMITHTUNE_NOTES.md): the Student is trained locally on smithtune's splits.
Each trajectory becomes one example per assistant turn (history + tools), to be trained
with --mask-prompt so only that turn is learned, as smithtune does.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from langchain_core.utils.function_calling import convert_to_openai_tool

from ..extractor.tools import TOOLS

KEEP = ("role", "content", "tool_calls", "tool_call_id", "name")


def _text(content) -> str:
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def normalize(message: dict) -> dict:
    """OpenAI-style message → what Qwen's chat template expects (tool-call arguments as objects)."""
    m = {k: v for k, v in message.items() if k in KEEP}
    m["content"] = _text(m.get("content"))
    if m.get("tool_calls"):
        m["tool_calls"] = [
            {"type": "function",
             "function": {"name": call["function"]["name"],
                          "arguments": (json.loads(call["function"]["arguments"])
                                        if isinstance(call["function"]["arguments"], str)
                                        else call["function"]["arguments"])}}
            for call in m["tool_calls"]
        ]
    return m


def expand(trajectory: dict, tools: list[dict]) -> list[dict]:
    messages = [normalize(m) for m in trajectory["messages"]]
    return [{"messages": messages[: i + 1], "tools": tools}
            for i, m in enumerate(messages) if m["role"] == "assistant"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prepared", type=Path, default=Path("runs/smithtune/golden/prepared"))
    p.add_argument("--out", type=Path, default=Path("data/student-sft"))
    args = p.parse_args()
    tools = [convert_to_openai_tool(t) for t in TOOLS]
    args.out.mkdir(parents=True, exist_ok=True)
    for src, dst in (("train", "train"), ("validation", "valid")):
        trajectories = [json.loads(line) for line in (args.prepared / f"{src}.jsonl").open(encoding="utf-8")]
        rows = [row for t in trajectories for row in expand(t, tools)]
        with (args.out / f"{dst}.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{src}: {len(trajectories)} trajectories -> {len(rows)} examples -> {args.out / f'{dst}.jsonl'}")


if __name__ == "__main__":
    main()

"""A scripted stand-in for the LLM (Pydantic AI ``FunctionModel``): one lookup,
one what-if, then copies tool numbers into the typed output. Used by the tests
and by ``scripts/evaluate_agents.py --model scripted`` for a no-LLM dry run.
It is not a baseline for judgment.
"""

from __future__ import annotations

import re

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo

def _returns(messages) -> list[ToolReturnPart]:
    return [p for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart)]


def _user_text(messages) -> str:
    return "\n".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if type(p).__name__ == "UserPromptPart")


def scripted_agent(messages, info: AgentInfo) -> ModelResponse:
    """A fake LLM that behaves like a careful agent: looks things up with the
    tools, then copies the tool numbers into its typed output."""
    tools = {t.name for t in info.function_tools}
    out = info.output_tools[0].name if info.output_tools else None
    rets = _returns(messages)
    if "try_plan" in tools:  # maintenance
        if not rets:
            return ModelResponse(parts=[ToolCallPart("rank_sections", {"by": "requests", "plan_filter": "not_in_plan", "limit": 3})])
        if len(rets) == 1:
            top = rets[0].content[0]
            return ModelResponse(parts=[ToolCallPart("try_plan", {"add": [top.section_id], "remove": []})])
        top = rets[0].content[0]
        return ModelResponse(parts=[ToolCallPart(out, {
            "deviations": [{"section_id": top.section_id, "action": "add",
                            "reason": f"{top.requests} requests, condition {top.condition}"}],
            "rationale": "One high-request street added.",
        })])
    if "closure_impact" in tools:  # closure
        works = re.findall(r"^- (S\d+)", _user_text(messages), flags=re.M)
        cap = int(re.search(r"CAP = (\d+)", _user_text(messages)).group(1))
        months = {m + 1: works[m::3] for m in range(3)}
        assert all(len(v) <= cap for v in months.values())
        if not rets:
            return ModelResponse(parts=[ToolCallPart("closure_impact", {"section_ids": v}) for v in months.values() if v])
        reps = [r.content for r in rets]
        phases = [{"month": m, "section_ids": v, "trips_affected": r.trips_affected, "total_delay_s": r.total_delay_s,
                   "hospital_nodes_lost": r.hospital_nodes_lost, "school_nodes_lost": r.school_nodes_lost}
                  for (m, v), r in zip([(m, v) for m, v in months.items() if v], reps)]
        flags = [{"month": p["month"], "facility": "hospital", "section_ids": p["section_ids"],
                  "nodes_lost": p["hospital_nodes_lost"], "note": "keep one lane open"} for p in phases if p["hospital_nodes_lost"]]
        return ModelResponse(parts=[ToolCallPart(out, {"phases": phases, "flags": flags, "rationale": "Round-robin by criticality."})])
    # coordinator: cite the first number of the fact sheet's value line verbatim
    facts = _user_text(messages)
    share = re.search(r"Value captured: ([\d.]+)%", facts).group(1)
    return ModelResponse(parts=[ToolCallPart(out, {
        "summary": f"The plan captures {share}% of the value.",
        "trade_offs": [{"topic": "requests", "decision": "added one street", "cost": "some value"}],
        "risks": ["made-up number 123.45"],
    })])

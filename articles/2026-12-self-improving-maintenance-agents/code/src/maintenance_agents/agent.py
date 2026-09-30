"""The diagnosis agent: Pydantic AI, typed output, tools cut at decision time.

It reads one anomaly episode (``episodes.Situation``), optionally a block of
past episodes from memory, and answers with a ``Diagnosis``. Tools fetch the
residual time series of any component group, the context signals and the
turbine's maintenance log, all limited to what was known at decision time.

Model: ``$AGENT_BASE_URL`` / ``$AGENT_MODEL`` (any OpenAI-compatible server),
by default the local mlx-lm server at http://localhost:8088/v1 serving
Qwen3-8B (4-bit) as ``default_model``. Qwen3 thinking is switched off with
``chat_template_kwargs.enable_thinking = false``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, PromptedOutput, RunContext, ToolOutput
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .episodes import ReplayData, Situation
from .memory import Candidate

Component = Literal["generator", "generator_bearing", "gearbox", "hydraulic_group", "transformer", "none"]
Group = Literal["generator", "generator_bearing", "gearbox", "hydraulic", "hub", "transformer", "converter", "nacelle"]


class Diagnosis(BaseModel):
    component: Component = Field(
        description="The logbook component you think is failing, or 'none' if you think nothing is failing"
    )
    action: Literal["inspect", "monitor", "ignore"] = Field(
        description="inspect: open a work order to inspect that component soon; monitor: no work order, keep watching; "
        "ignore: noise, weather, a sensor artefact or normal behaviour after a repair"
    )
    urgency: Literal["low", "medium", "high"] = Field(description="How soon someone should act")
    evidence: str = Field(description="One or two sentences: the signals, log entries and past cases behind the decision")
    confidence: float = Field(ge=0, le=1, description="How sure you are, 0 to 1")


INSTRUCTIONS = """\
You are the maintenance engineer on call for a 5-turbine onshore wind farm. An anomaly detector flagged a day on one turbine.
Decide what failing component (if any) it points to and what to do.

How the detector works: a normal-behaviour model predicts each temperature's rise over ambient from wind, power, rotor speed and recent load.
The residual z is how far the measured temperature is from that prediction, in robust standard deviations of recent normal weeks.
Positive z = hotter than expected. An Isolation Forest on the residuals gives the day score; alarm above 2.5.

Signal groups -> logbook component:
- generator: stator winding L1-L3, split ring chamber -> generator
- generator_bearing: generator bearing DE / NDE -> generator_bearing
- gearbox: gearbox HSS bearing, gearbox oil -> gearbox
- hydraulic: hydraulic group oil; hub: hub controller, nose cone -> hydraulic_group (the hydraulic group sits in the hub; pitch and brake circuit)
- transformer: HV transformer L1-L3 -> transformer
- converter, nacelle: context only (no logbook component)

Rules:
- A residual alarm is not proof of a failure. Weather, grid events, sensor faults and repairs also move residuals.
- The largest residual is not always the failing part; heat and sensor faults spread between neighbouring parts.
- Use the tools when the first-day summary is not enough (the series before the alarm, the context signals, the maintenance log).
- Past episodes, if shown, come from this farm's history with what the logbook recorded afterwards. They are evidence, not rules: use them only if they really resemble this case.
- Answer in English.
"""


@dataclass
class Deps:
    data: ReplayData
    situation: Situation


def residual_series(ctx: RunContext[Deps], group: Group, days: int = 14) -> str:
    """Daily residual z of one signal group on this turbine, for the `days` days up to the first alarm day (max 60)."""
    return ctx.deps.data.residual_series(ctx.deps.situation, group, days)


def context_signals(ctx: RunContext[Deps]) -> str:
    """Converter/nacelle residuals, hours of data, and the other turbines' detector scores on the first alarm day."""
    return ctx.deps.data.context(ctx.deps.situation)


def maintenance_log(ctx: RunContext[Deps]) -> str:
    """This turbine's failure logbook entries recorded before now (last 5)."""
    return ctx.deps.data.maintenance_log(ctx.deps.situation)


TOOLS = (residual_series, context_signals, maintenance_log)


def local_model():
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=os.environ.get("AGENT_BASE_URL", "http://localhost:8088/v1"),
        api_key=os.environ.get("AGENT_API_KEY", "local"),
    )
    return OpenAIChatModel(os.environ.get("AGENT_MODEL", "default_model"), provider=provider)


def model_settings() -> dict:
    return {
        "temperature": 0.0,
        "max_tokens": 1024,
        "timeout": 900,
        # Qwen3 thinks by default; off, as in the other articles. Ignored by servers that don't know it.
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }


def build_agent(model=None, *, output_mode: Literal["tool", "prompted"] = "tool", tools: bool = True) -> Agent[Deps, Diagnosis]:
    output = ToolOutput(Diagnosis, name="final_diagnosis") if output_mode == "tool" else PromptedOutput(Diagnosis)
    return Agent(
        model if model is not None else local_model(),
        deps_type=Deps,
        output_type=output,
        instructions=INSTRUCTIONS,
        tools=list(TOOLS) if tools else [],
        retries=3,
        model_settings=model_settings(),
    )


# ---------------------------------------------------------------- prompt


def memory_block(selected: list[Candidate], gated: bool) -> str:
    if not selected:
        return (
            "Past episodes: none passed the memory filter for this case."
            if gated
            else "Past episodes: none yet."
        )
    lines = ["Past episodes from this farm, most similar first (similarity = cosine of the first-day residual patterns, 1 = identical):"]
    for i, c in enumerate(selected, 1):
        s, d, v = c.view.situation, c.view.record.diagnosis, c.view
        out = f"Outcome: {v.outcome.text()}. Lesson: {v.lesson}" if v.outcome is not None else "Outcome: not known yet."
        lines.append(
            f"{i}. Episode #{s.episode_id}, {s.summary()}. Similarity {c.similarity:.2f}, {c.age_days:.0f} days ago.\n"
            f"   Diagnosis then: {d['action']} {d['component']} (urgency {d['urgency']}, confidence {d['confidence']:.2f}).\n"
            f"   {out}"
        )
    return "\n".join(lines)


def render_prompt(s: Situation, memories: list[Candidate] | None, *, gated: bool = False, prefetch: str | None = None) -> str:
    parts = [
        (
            f"Anomaly episode #{s.episode_id} on turbine {s.turbine_id}. First alarm day: {s.start.date()}. "
            f"You are deciding at {s.decision_time:%Y-%m-%d %H:%M}, with data up to then."
        ),
        f"Detector score that day: {s.score:.1f} (alarm above 2.5).",
        f"Top residual signals that day (z): {s.top_signals or 'n/a'}.",
        f"Top signal group: {s.top_group} -> logbook component {s.top_component}." if s.top_group else "Top signal group: n/a.",
        f"Top context signal: {s.context_signal or 'n/a'}.",
    ]
    if prefetch:
        parts.append(prefetch)
    if memories is not None:
        parts.append(memory_block(memories, gated))
    parts.append("Give your diagnosis.")
    return "\n".join(parts)


def prefetch_context(data: ReplayData, s: Situation) -> str:
    """The same information the tools give, placed in the prompt (``--context prefetch``)."""
    series = data.residual_series(s, s.top_group, 14) if s.top_group else "no data"
    return "\n".join(
        ["Context signals:", data.context(s), "Maintenance log:", data.maintenance_log(s), "Top group, last 14 days:", series]
    )


# ---------------------------------------------------------------- offline stand-in


_MEM = re.compile(r"Outcome: logbook failure on \S+, component (\w+)")
_TOP = re.compile(r"-> logbook component (\w+)\.")


def rule_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Deterministic, offline stand-in for the LLM (harness dry runs, never reported as the agent).

    Reads only the prompt text: if a shown past episode ended in a logbook
    failure, copy the most similar one's component and inspect; otherwise use
    the detector's top component and monitor.
    """
    prompt = "\n".join(
        p.content for m in messages for p in getattr(m, "parts", []) if getattr(p, "part_kind", "") == "user-prompt" and isinstance(p.content, str)
    )
    mem = _MEM.findall(prompt)
    top = _TOP.search(prompt)
    if mem:
        args = {"component": mem[0], "action": "inspect", "urgency": "medium", "evidence": "a similar past episode ended in a failure", "confidence": 0.6}
    else:
        comp = top.group(1) if top and top.group(1) != "None" else "none"
        args = {"component": comp, "action": "monitor", "urgency": "low", "evidence": "detector top group", "confidence": 0.3}
    if info.output_tools:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])
    import json

    return ModelResponse(parts=[TextPart(json.dumps(args))])


def rule_model() -> FunctionModel:
    return FunctionModel(rule_function, model_name="rule-stand-in")

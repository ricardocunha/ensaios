"""The three LLM agents (Pydantic AI, typed outputs) and the pipeline that
chains them into a quarterly plan.

- **Maintenance-priority agent**: starts from the solver plan at a budget and
  proposes *deviations* (add / remove sections), each with a reason. The
  final plan is rebuilt deterministically: ``solve_budget`` with the adds
  forced in and the removals excluded, so budget feasibility and the fill-up
  of the remaining budget are never the LLM's job.
- **Closure-impact agent**: gets the plan's major works (highest
  criticality) and assigns them to the quarter's three months, with a
  per-month capacity, to limit simultaneous impact. It must state each
  month's combined impact numbers and flag hospital/school access losses.
- **Planning coordinator**: gets both outputs plus a fact sheet computed by
  the tools and writes the quarterly plan with the trade-offs spelled out.

Hand-off between agents is programmatic (the pipeline passes typed outputs
on), not agent-calls-agent: fewer moving parts for an 8B local model.

Every tool call's numeric output is recorded in ``Deps.ledger`` so
``audit.py`` can check each number the agents cite.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext, capture_run_messages
from pydantic_ai.usage import UsageLimits

from road_agents import planning as P

N_MONTHS = 3
N_MAJOR_WORKS = 15


# --- model -----------------------------------------------------------------------


def local_model(base_url: str | None = None, model_name: str | None = None):
    """Qwen3-8B behind mlx-lm's OpenAI-compatible server (no key, no cost)."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=base_url or os.environ.get("ROAD_AGENTS_BASE_URL", "http://localhost:8088/v1"),
        api_key=os.environ.get("ROAD_AGENTS_API_KEY", "local"),
    )
    return OpenAIChatModel(model_name or os.environ.get("ROAD_AGENTS_MODEL", "default_model"), provider=provider)


def model_settings(temperature: float = 0.7, max_tokens: int = 2048) -> dict:
    # Qwen3's recommended non-thinking sampling (temperature 0.7, top_p 0.8);
    # thinking off, as on a shared laptop server it costs minutes per call.
    return {
        "temperature": temperature,
        "top_p": 0.8,
        "max_tokens": max_tokens,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }


# --- deps and ledger -------------------------------------------------------------


@dataclass
class Deps:
    data: P.PlanningData
    budget_share: float
    solver: P.PlanResult
    works: list[str] = field(default_factory=list)  # closure agent: works to sequence
    final_plan: P.PlanResult | None = None
    ledger: list[float] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    @property
    def solver_set(self) -> set[str]:
        return set(self.solver.chosen)

    def record(self, agent: str, tool: str, args: dict, out: Any) -> Any:
        self.ledger.extend(numbers_in(out))
        self.calls.append({"agent": agent, "tool": tool, "args": args})
        return out


def numbers_in(obj: Any) -> list[float]:
    """Every number inside a tool output (models, dicts, lists, text)."""
    from road_agents.audit import extract_numbers

    if isinstance(obj, BaseModel):
        obj = obj.model_dump()
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        return [n.value for n in extract_numbers(obj)]
    if isinstance(obj, dict):
        return [x for v in obj.values() for x in numbers_in(v)]
    if isinstance(obj, (list, tuple)):
        return [x for v in obj for x in numbers_in(v)]
    return []


# --- output types ------------------------------------------------------------------


class Deviation(BaseModel):
    section_id: str = Field(description="Section id, e.g. S01234")
    action: Literal["add", "remove"] = Field(description="add = not in the solver plan, force it in; remove = drop it from the solver plan")
    reason: str = Field(description="Why, citing the tool numbers that justify it (condition, requests, criticality, value, cost)")


class MaintenanceProposal(BaseModel):
    deviations: list[Deviation] = Field(default_factory=list, max_length=12, description="Empty if the solver plan should stand")
    rationale: str = Field(description="Two to four sentences on the overall choice, with numbers from the tools")


class Phase(BaseModel):
    month: int = Field(ge=1, le=N_MONTHS)
    section_ids: list[str]
    trips_affected: int = Field(description="From closure_impact on exactly this month's sections")
    total_delay_s: float = Field(description="From closure_impact on exactly this month's sections")
    hospital_nodes_lost: int = Field(description="From closure_impact on exactly this month's sections")
    school_nodes_lost: int = Field(description="From closure_impact on exactly this month's sections")


class AccessFlag(BaseModel):
    month: int = Field(ge=1, le=N_MONTHS)
    facility: Literal["hospital", "school"]
    section_ids: list[str] = Field(description="The works responsible")
    nodes_lost: int
    note: str = Field(description="What to do about it (detour, night work, keep one lane open)")


class ClosureSchedule(BaseModel):
    phases: list[Phase]
    flags: list[AccessFlag] = Field(default_factory=list)
    rationale: str


class TradeOff(BaseModel):
    topic: str
    decision: str
    cost: str = Field(description="What the decision gives up, with numbers from the fact sheet")


class QuarterlyPlan(BaseModel):
    summary: str = Field(description="Three to five sentences for a city engineer")
    trade_offs: list[TradeOff] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)


# --- maintenance agent --------------------------------------------------------------

MAINTENANCE_INSTRUCTIONS = """\
You are the maintenance-priority agent for Belo Horizonte's road network.
A knapsack solver has already chosen which road sections to resurface this year within the budget,
maximizing value = condition x criticality x km, where condition is a 0-1 percentile of pothole-request
density (citizen requests, which over-represent residential streets) and criticality is 0-1 sampled
travel-time betweenness. Repair costs are synthetic cost units.

Your job: decide whether to deviate from the solver plan. You may add sections the solver left out or
remove sections it chose, but only when the tool numbers show something the value score misses.
Every deviation loses value by construction; say what it buys. Proposing no deviation is a valid answer.

Rules:
- Use the tools to look at sections; never invent section ids or numbers.
- Before finishing, call try_plan with your adds and removes to see the value it costs.
- In each reason, cite the numbers you got from the tools (requests, condition, criticality, value, cost).
- At most 6 deviations.
"""


def maintenance_agent(model=None, settings: dict | None = None) -> Agent[Deps, MaintenanceProposal]:
    agent = Agent(
        model,
        deps_type=Deps,
        output_type=MaintenanceProposal,
        instructions=MAINTENANCE_INSTRUCTIONS,
        retries=2,
        model_settings=settings if settings is not None else model_settings(),
        name="maintenance",
        defer_model_check=True,
    )

    @agent.tool
    def rank_sections(
        ctx: RunContext[Deps],
        by: P.RankBy = "value",
        limit: int = 10,
        plan_filter: P.PlanFilter = "any",
        highway: str | None = None,
        name_contains: str | None = None,
    ) -> list[P.SectionRow]:
        """Top sections sorted by `by` (value, value_per_cost, condition, criticality or requests).
        plan_filter: 'in_plan' / 'not_in_plan' restricts to sections the solver chose or left out.
        highway: OSM class such as residential, tertiary, primary, trunk. limit: at most 50."""
        args = dict(by=by, limit=limit, plan_filter=plan_filter, highway=highway, name_contains=name_contains)
        out = P.rank_sections(ctx.deps.data, plan=ctx.deps.solver_set, **args)
        return ctx.deps.record("maintenance", "rank_sections", args, out)

    @agent.tool
    def get_section(ctx: RunContext[Deps], section_id: str) -> P.SectionDetail:
        """All fields of one section, including its share of the budget and its value/cost rank."""
        try:
            out = P.section_details(ctx.deps.data, section_id, ctx.deps.solver_set, ctx.deps.solver.budget)
        except KeyError as e:
            raise ModelRetry(str(e)) from e
        return ctx.deps.record("maintenance", "get_section", {"section_id": section_id}, out)

    @agent.tool
    def try_plan(ctx: RunContext[Deps], add: list[str], remove: list[str]) -> str:
        """Re-solve the budget with `add` forced in and `remove` excluded; returns the plan summary
        and its value relative to the solver plan."""
        try:
            p = P.solve_budget(ctx.deps.data, ctx.deps.budget_share, add, remove)
        except (KeyError, ValueError) as e:
            raise ModelRetry(str(e)) from e
        p = P.with_solver_comparison(p, ctx.deps.solver)
        out = P.plan_summary_text(ctx.deps.data, p)
        return ctx.deps.record("maintenance", "try_plan", {"add": add, "remove": remove}, out)

    @agent.output_validator
    def check(ctx: RunContext[Deps], out: MaintenanceProposal) -> MaintenanceProposal:
        errors = validate_proposal(ctx.deps, out)
        if errors:
            raise ModelRetry("; ".join(errors))
        return out

    return agent


def validate_proposal(deps: Deps, out: MaintenanceProposal) -> list[str]:
    errors = []
    known = deps.data.sections.index
    seen = set()
    for d in out.deviations:
        if d.section_id not in known:
            errors.append(f"{d.section_id} is not a section id")
            continue
        if d.section_id in seen:
            errors.append(f"{d.section_id} appears twice")
        seen.add(d.section_id)
        if d.action == "add" and d.section_id in deps.solver_set:
            errors.append(f"{d.section_id} is already in the solver plan; it cannot be added")
        if d.action == "remove" and d.section_id not in deps.solver_set:
            errors.append(f"{d.section_id} is not in the solver plan; it cannot be removed")
        if not d.reason.strip():
            errors.append(f"{d.section_id} has no reason")
    if not errors:
        adds, removes = split_deviations(out)
        try:
            P.solve_budget(deps.data, deps.budget_share, adds, removes)
        except ValueError as e:
            errors.append(str(e))
    return errors


def split_deviations(out: MaintenanceProposal) -> tuple[list[str], list[str]]:
    adds = [d.section_id for d in out.deviations if d.action == "add"]
    removes = [d.section_id for d in out.deviations if d.action == "remove"]
    return adds, removes


def maintenance_prompt(deps: Deps) -> str:
    return (
        f"Budget: {100 * deps.budget_share:g}% of the total repair cost of all candidate sections.\n"
        f"Solver plan:\n{P.plan_summary_text(deps.data, deps.solver)}\n\n"
        "Look at what the solver chose and what it left out (for example the sections with the most "
        "pothole requests), then return your MaintenanceProposal."
    )


# --- closure-impact agent ----------------------------------------------------------------

CLOSURE_INSTRUCTIONS = f"""\
You are the closure-impact agent. The planned works below close whole road sections while they run.
Assign every work to one of the quarter's {N_MONTHS} months; works in the same month are closed at the same time.

Goals, in order:
1. No month may cut hospital (10-min) or school (5-min) access that no single work cuts on its own:
   do not put works whose combined closure strands or cuts off extra nodes in the same month
   (adjacent sections of the same avenue are the usual culprits).
2. Keep the worst month's combined total delay low; spread the heavy works.

Rules:
- Each work goes in exactly one month; at most CAP works per month (CAP is given below).
- Use check_schedule to score a whole candidate schedule and closure_impact for one month's grouping;
  the tools are exact, you are not. If check_schedule reports a VIOLATION, move one work of each
  conflicting pair to another month (swap it with a work there to respect CAP) and check again.
  Do not re-check a schedule you have already checked.
- For each month, copy trips_affected, total_delay_s, hospital_nodes_lost and school_nodes_lost from a
  closure_impact call on exactly that month's section ids. Never estimate these numbers.
- Add a flag for every month with hospital_nodes_lost > 0 or school_nodes_lost > 0.
"""


def closure_agent(model=None, settings: dict | None = None) -> Agent[Deps, ClosureSchedule]:
    agent = Agent(
        model,
        deps_type=Deps,
        output_type=ClosureSchedule,
        instructions=CLOSURE_INSTRUCTIONS,
        retries=3,
        model_settings=settings if settings is not None else model_settings(),
        name="closure",
        defer_model_check=True,
    )

    @agent.tool
    def closure_impact(ctx: RunContext[Deps], section_ids: list[str]) -> P.ClosureReport:
        """Exact impact of closing all these sections at the same time: sampled trips affected and
        delayed, and graph nodes that lose 10-min hospital / 5-min school access."""
        try:
            out = P.closure_report(ctx.deps.data, section_ids)
        except (KeyError, ValueError) as e:
            raise ModelRetry(str(e)) from e
        return ctx.deps.record("closure", "closure_impact", {"section_ids": section_ids}, out)

    @agent.tool
    def check_schedule(ctx: RunContext[Deps], month_1: list[str], month_2: list[str], month_3: list[str]) -> str:
        """Score a whole candidate schedule: each month's combined closure impact, access lost only because
        works overlap (a violation), and the worst month's total delay."""
        months = {1: month_1, 2: month_2, 3: month_3}
        try:
            rep = P.schedule_report(ctx.deps.data, months)
        except (KeyError, ValueError) as e:
            raise ModelRetry(str(e)) from e
        out = P.schedule_summary_text(rep)
        return ctx.deps.record("closure", "check_schedule", {"months": months}, out)

    @agent.tool
    def accessibility_loss(ctx: RunContext[Deps], section_ids: list[str], facility: P.Facility = "hospital") -> P.AccessLoss:
        """Nodes that lose access to the nearest hospital (10 min) or school (5 min) when these sections close together."""
        try:
            out = P.accessibility_loss_sections(ctx.deps.data, section_ids, facility)
        except KeyError as e:
            raise ModelRetry(str(e)) from e
        return ctx.deps.record("closure", "accessibility_loss", {"section_ids": section_ids, "facility": facility}, out)

    @agent.tool
    def get_section(ctx: RunContext[Deps], section_id: str) -> P.SectionDetail:
        """All fields of one section."""
        try:
            out = P.section_details(ctx.deps.data, section_id)
        except KeyError as e:
            raise ModelRetry(str(e)) from e
        return ctx.deps.record("closure", "get_section", {"section_id": section_id}, out)

    @agent.output_validator
    def check(ctx: RunContext[Deps], out: ClosureSchedule) -> ClosureSchedule:
        errors = validate_schedule(ctx.deps.works, out)
        if errors:
            raise ModelRetry("; ".join(errors))
        return out

    return agent


def validate_schedule(works: list[str], out: ClosureSchedule) -> list[str]:
    cap = P.phase_capacity(len(works), N_MONTHS)
    errors = []
    months = [p.month for p in out.phases]
    if len(set(months)) != len(months):
        errors.append("each month must appear once")
    assigned = [s for p in out.phases for s in p.section_ids]
    missing = sorted(set(works) - set(assigned))
    extra = sorted(set(assigned) - set(works))
    dup = sorted({s for s in assigned if assigned.count(s) > 1})
    if missing:
        errors.append(f"works not scheduled: {missing}")
    if extra:
        errors.append(f"not in the works list: {extra}")
    if dup:
        errors.append(f"scheduled more than once: {dup}")
    over = [p.month for p in out.phases if len(p.section_ids) > cap]
    if over:
        errors.append(f"months over capacity {cap}: {over}")
    return errors


def schedule_dict(out: ClosureSchedule) -> dict[int, list[str]]:
    return {p.month: list(p.section_ids) for p in out.phases}


def closure_prompt(deps: Deps) -> tuple[str, list[P.ClosureReport]]:
    singles = [P.closure_report(deps.data, [s]) for s in deps.works]
    rows = []
    for s, r in zip(deps.works, singles):
        d = deps.data.sections.loc[s]
        rows.append(
            f"- {s} {d['name'] or '(unnamed)'} ({d['highway']}, {d['length_m']:.0f} m): alone -> "
            f"{r.trips_affected} trips affected, total delay {r.total_delay_s} s, "
            f"hospital nodes lost {r.hospital_nodes_lost}, school nodes lost {r.school_nodes_lost}"
        )
    cap = P.phase_capacity(len(deps.works), N_MONTHS)
    text = (
        f"{len(deps.works)} major works (the plan's highest-criticality sections), CAP = {cap} per month.\n"
        "Single-closure impact of each work (closure_impact on that section alone, "
        f"{singles[0].n_trips_sampled if singles else 0} sampled trips):\n" + "\n".join(rows) +
        "\n\nReturn the ClosureSchedule."
    )
    return text, singles


# --- coordinator -----------------------------------------------------------------------------

COORDINATOR_INSTRUCTIONS = """\
You are the planning coordinator. Combine the maintenance proposal and the closure schedule into a quarterly
plan for Belo Horizonte's road works. Spell out the trade-offs: value given up by each deviation from the
solver, requests covered, delay and access risks of the schedule. Use only numbers that appear in the fact
sheet or in tool outputs; copy them as written. If a number is not there, say so instead of estimating.
"""


def coordinator_agent(model=None, settings: dict | None = None) -> Agent[Deps, QuarterlyPlan]:
    agent = Agent(
        model,
        deps_type=Deps,
        output_type=QuarterlyPlan,
        instructions=COORDINATOR_INSTRUCTIONS,
        retries=2,
        model_settings=settings if settings is not None else model_settings(),
        name="coordinator",
        defer_model_check=True,
    )

    @agent.tool
    def get_section(ctx: RunContext[Deps], section_id: str) -> P.SectionDetail:
        """All fields of one section."""
        try:
            out = P.section_details(ctx.deps.data, section_id, ctx.deps.solver_set, ctx.deps.solver.budget)
        except KeyError as e:
            raise ModelRetry(str(e)) from e
        return ctx.deps.record("coordinator", "get_section", {"section_id": section_id}, out)

    return agent


def fact_sheet(
    deps: Deps,
    proposal: MaintenanceProposal,
    final: P.PlanResult,
    schedule: ClosureSchedule | None,
    sched_report: P.ScheduleReport | None,
    agent_text: bool = True,
) -> str:
    """Tool-computed facts for the coordinator. With ``agent_text=False`` the
    upstream agents' own words (reasons, flag notes) are left out: that is the
    version whose numbers enter the audit ledger, so an agent's claim never
    grounds itself."""
    lines = ["SOLVER PLAN", P.plan_summary_text(deps.data, deps.solver), "", "FINAL PLAN (after deviations)",
             P.plan_summary_text(deps.data, final), "", "DEVIATIONS"]
    for d in proposal.deviations:
        r = deps.data.sections.loc[d.section_id]
        lines.append(
            f"- {d.action} {d.section_id} {r['name'] or '(unnamed)'} ({r['highway']}): requests {int(r['requests'])}, "
            f"condition {r['condition']:.3f}, criticality {r['criticality']:.4f}, value {r['value']:.5f}, "
            f"cost {r['repair_cost']:.1f}." + (f" Agent's reason: {d.reason}" if agent_text else "")
        )
    if not proposal.deviations:
        lines.append("- none (the solver plan stands)")
    lines += ["", "CLOSURE SCHEDULE (recomputed by the tools)"]
    if sched_report is None:
        lines.append("- not available (the closure agent failed)")
    else:
        for ph in sched_report.phases:
            lines.append(f"- month {ph.month}: " + P.closure_summary_text(ph.impact)
                         + f" Access lost only because works overlap: hospital {ph.hospital_interaction_nodes},"
                         f" school {ph.school_interaction_nodes} nodes.")
        lines.append(f"Worst month combined total delay: {sched_report.peak_total_delay_s} s.")
    if agent_text and schedule is not None and schedule.flags:
        lines.append("Closure agent's flags: " + "; ".join(
            f"month {f.month} {f.facility} {f.nodes_lost} nodes ({', '.join(f.section_ids)}): {f.note}" for f in schedule.flags))
    return "\n".join(lines)


# --- pipeline ---------------------------------------------------------------------------------


@dataclass
class AgentRun:
    name: str
    ok: bool
    output: BaseModel | None
    seconds: float
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    error: str | None = None
    transcript: list[dict] = field(default_factory=list)


def transcript(messages, max_chars: int = 600) -> list[dict]:
    """Compact log of a run: tool calls with args, tool returns, retry prompts, text."""
    out = []
    for m in messages:
        for p in getattr(m, "parts", []):
            kind = type(p).__name__
            if kind == "ToolCallPart":
                out.append({"kind": "call", "tool": p.tool_name, "args": str(p.args)[:max_chars]})
            elif kind == "ToolReturnPart":
                out.append({"kind": "return", "tool": p.tool_name, "content": str(p.content)[:max_chars]})
            elif kind == "RetryPromptPart":
                out.append({"kind": "retry", "tool": getattr(p, "tool_name", None), "content": str(p.content)[:max_chars]})
            elif kind == "TextPart":
                out.append({"kind": "text", "content": p.content[:max_chars]})
    return out


@dataclass
class PipelineResult:
    budget_share: float
    solver: P.PlanResult
    final: P.PlanResult
    works: list[str]
    maintenance: AgentRun
    closure: AgentRun
    coordinator: AgentRun
    ledger: list[float]
    calls: list[dict]
    closure_prompt_singles: list[P.ClosureReport]
    facts: str = ""


def _run(agent: Agent, prompt: str, deps: Deps, limit: int) -> AgentRun:
    t = time.perf_counter()
    with capture_run_messages() as messages:
        try:
            res = agent.run_sync(prompt, deps=deps, usage_limits=UsageLimits(request_limit=limit))
        except Exception as e:  # a failed agent is a result, not a crash
            n_req = sum(type(m).__name__ == "ModelResponse" for m in messages)
            return AgentRun(agent.name or "?", False, None, time.perf_counter() - t, requests=n_req,
                            error=f"{type(e).__name__}: {e}"[:2000], transcript=transcript(messages))
    u = res.usage
    return AgentRun(
        agent.name or "?", True, res.output, time.perf_counter() - t,
        requests=getattr(u, "requests", 0), input_tokens=getattr(u, "input_tokens", 0),
        output_tokens=getattr(u, "output_tokens", 0), tool_calls=getattr(u, "tool_calls", 0),
        transcript=transcript(res.all_messages()),
    )


def run_pipeline(
    data: P.PlanningData,
    budget_share: float,
    model=None,
    settings: dict | None = None,
    limits: dict[str, int] | None = None,
    n_works: int = N_MAJOR_WORKS,
) -> PipelineResult:
    limits = {"maintenance": 12, "closure": 14, "coordinator": 4, **(limits or {})}
    solver = P.solve_budget(data, budget_share)
    deps = Deps(data, budget_share, solver)
    # numbers the model sees in instructions and schema descriptions count as context, not claims
    deps.ledger.extend(numbers_in(MAINTENANCE_INSTRUCTIONS + CLOSURE_INSTRUCTIONS + COORDINATOR_INSTRUCTIONS))
    deps.ledger.extend([2022.0, 2023.0, data.hospital_s, data.school_s, data.hospital_s / 60, data.school_s / 60])

    # 1. maintenance agent
    deps.ledger.extend(numbers_in(maintenance_prompt(deps)))
    m = _run(maintenance_agent(model, settings), maintenance_prompt(deps), deps, limits["maintenance"])
    proposal = m.output if m.ok else MaintenanceProposal(deviations=[], rationale="(maintenance agent failed)")
    adds, removes = split_deviations(proposal)
    final = P.with_solver_comparison(P.solve_budget(data, budget_share, adds, removes), solver)
    deps.final_plan = final

    # 2. closure agent on the final plan's major works
    deps.works = P.major_works(data, final.chosen, n_works)
    prompt, singles = closure_prompt(deps)
    deps.ledger.extend(numbers_in(prompt))
    c = _run(closure_agent(model, settings), prompt, deps, limits["closure"])
    schedule = c.output if c.ok else None
    sched_report = P.schedule_report(data, schedule_dict(schedule)) if schedule else None

    # 3. coordinator
    facts = fact_sheet(deps, proposal, final, schedule, sched_report)
    deps.ledger.extend(numbers_in(fact_sheet(deps, proposal, final, schedule, sched_report, agent_text=False)))
    co = _run(coordinator_agent(model, settings), f"FACT SHEET\n{facts}\n\nReturn the QuarterlyPlan.", deps, limits["coordinator"])

    return PipelineResult(budget_share, solver, final, deps.works, m, c, co, deps.ledger, deps.calls, singles, facts)


def dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    return obj


def result_json(r: PipelineResult) -> dict:
    def run(a: AgentRun) -> dict:
        return {"ok": a.ok, "seconds": round(a.seconds, 2), "requests": a.requests, "input_tokens": a.input_tokens,
                "output_tokens": a.output_tokens, "tool_calls": a.tool_calls, "error": a.error, "output": dump(a.output),
                "transcript": a.transcript}

    return {
        "budget_share": r.budget_share,
        "solver": {**r.solver.model_dump(), "chosen_n": len(r.solver.chosen)},
        "final": {**r.final.model_dump(), "chosen": r.final.chosen},
        "works": r.works,
        "maintenance": run(r.maintenance),
        "closure": run(r.closure),
        "coordinator": run(r.coordinator),
        "calls": r.calls,
        "ledger_size": len(r.ledger),
    }


def to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


"""Milestone 3: chronological replay of the anomaly episodes, three memory arms.

    uv run python -m maintenance_agents.replay --model rule            # offline dry run, no server
    uv run python -m maintenance_agents.replay --model local --limit 3 # smoke calls to the local server
    uv run python -m maintenance_agents.replay --model local           # the full run (77 episodes x 3 arms)
    uv run python -m maintenance_agents.replay --model local --prompt v2 --tag m3v2   # the v2 prompt (PLAN.md)

Arms:

* ``none``: no memory block at all.
* ``ungated``: the 3 most similar past episodes, whatever their outcome, age or turbine.
* ``gated``: ``memory.GATED`` (outcome known, similarity >= 0.5, <= 365 days old,
  same turbine or same top group, at most 3).

Each arm has its own memory and replays the episodes in decision-time order
(first alarm day + 1 day; ties by episode id). After each diagnosis the
episode, the diagnosis and its logbook outcome are written to memory; the
outcome is visible to later episodes only from its ``known_at`` time.

Output (git-ignored ``runs/``): ``<tag>_<arm>.jsonl`` (one row per episode, with
the prompt), ``<tag>_summary.json`` (metrics per arm). Labels are read only in
``score``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import pandas as pd
from pydantic_ai.usage import UsageLimits

from .episodes import ReplayData, Situation
from .memory import GATED, HORIZON_DAYS, UNGATED, GatePolicy, MemoryRecord, MemoryStore, gate, resolve_outcome, track_record

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"
ARMS: dict[str, GatePolicy | None] = {"none": None, "ungated": UNGATED, "gated": GATED}
REQUEST_LIMIT = 12  # model requests per episode (tool round trips + final answer)
INFRA_ERRORS = ("ModelAPIError", "APIConnectionError", "APITimeoutError", "ConnectError", "ReadTimeout", "Timeout")


async def diagnose(agent, prompt: str, deps, attempts: int = 3) -> tuple[dict | None, dict, str | None]:
    """One agent run -> (diagnosis, usage, error). Infra errors are retried with backoff."""
    err = None
    for i in range(attempts):
        try:
            r = await agent.run(prompt, deps=deps, usage_limits=UsageLimits(request_limit=REQUEST_LIMIT))
            u = r.usage
            usage = {"input_tokens": u.input_tokens or 0, "output_tokens": u.output_tokens or 0, "requests": u.requests, "tool_calls": u.tool_calls}
            tools = [p.tool_name for m in r.all_messages() for p in getattr(m, "parts", []) if getattr(p, "part_kind", "") == "tool-call"]
            usage["tools_called"] = tools
            return r.output.model_dump(), usage, None
        except Exception as e:  # noqa: BLE001 - recorded, not hidden
            err = f"{type(e).__name__}: {e}"[:500]
            if not any(k in type(e).__name__ or k in str(e) for k in INFRA_ERRORS):
                break
            await asyncio.sleep(10 * (i + 1))
    return None, {"input_tokens": 0, "output_tokens": 0, "requests": 0, "tool_calls": 0, "tools_called": []}, err


async def replay(
    data: ReplayData,
    agent,
    policy: GatePolicy | None,
    *,
    arm: str = "",
    situations: list[Situation] | None = None,
    horizon_days: int = HORIZON_DAYS,
    prefetch: bool = False,
    log_path: Path | None = None,
    done: dict[int, dict] | None = None,
    prompt_version: str = "v1",
) -> list[dict]:
    """Replay episodes in time order with one memory store. ``done`` reuses recorded diagnoses (resume)."""
    from .agent import Deps, prefetch_context, render_prompt

    situations = situations if situations is not None else data.situations()
    order = [(s.decision_time, s.episode_id) for s in situations]
    if order != sorted(order):
        raise ValueError("situations must be in decision-time order")
    store, rows = MemoryStore(), []
    resuming = bool(done)
    for s in situations:
        now = s.decision_time
        selected, reasons, n_visible, track = None, {}, 0, None
        if policy is not None:
            cands = store.candidates(s, now)
            n_visible = len(cands)
            g = gate(cands, s, policy)
            selected, reasons = g.selected, g.reasons()
            if prompt_version == "v2":
                track = track_record(cands, s, policy)
        prompt = render_prompt(
            s, selected, gated=policy is not None and policy.require_outcome, prefetch=prefetch_context(data, s) if prefetch else None, track=track
        )
        t0 = time.perf_counter()
        # resume: reuse recorded diagnoses only for an unbroken prefix whose prompts are unchanged;
        # from the first missing/failed episode on, everything is recomputed (memory depends on it)
        prev = (done or {}).get(s.episode_id)
        if resuming and prev is not None and prev.get("prompt") == prompt:
            diag, usage, err, seconds = prev["diagnosis"], prev["usage"], prev.get("error"), prev["seconds"]
        else:
            resuming = False
            diag, usage, err = await diagnose(agent, prompt, Deps(data, s, track))
            seconds = round(time.perf_counter() - t0, 2)
        outcome = resolve_outcome(s, data.faults, horizon_days)
        if diag is not None:
            store.add(MemoryRecord(situation=s, diagnosis=diag, decided_at=now, outcome=outcome))
        row = {
            "arm": arm,
            "episode_id": s.episode_id,
            "turbine_id": s.turbine_id,
            "start": str(s.start.date()),
            "decision_time": str(now),
            "top_group": s.top_group,
            "detector_component": s.top_component,
            "diagnosis": diag,
            "error": err,
            "memories": [
                {"episode_id": c.view.situation.episode_id, "similarity": round(c.similarity, 3), "age_days": round(c.age_days, 1), "outcome_known": c.view.outcome is not None}
                for c in (selected or [])
            ],
            "memories_visible": n_visible,
            "track_record": None
            if track is None
            else {"known": track.known, "failures": track.failures, "pending": track.pending, "components": track.failure_components, "mostly_nothing": track.mostly_nothing},
            "gate_rejections": reasons,
            "usage": usage,
            "seconds": seconds,
            "prompt": prompt,
        }
        rows.append(row)
        if log_path is not None:
            with log_path.open("a") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
    return rows


# ---------------------------------------------------------------- scoring


def episode_labels(runs_dir: Path = RUNS_DIR, tag: str = "m2") -> pd.DataFrame:
    """Scoring labels per episode: class and the components of the incident it precedes."""
    from .data import fault_events
    from .incidents import merge_incidents

    ev = pd.read_csv(runs_dir / f"{tag}_episodes_eval.csv")
    ev = ev[ev["detector"] == "iforest_resid"]
    comps = {int(i.incident_id): list(i.components) for i in merge_incidents(fault_events()).itertuples()}
    return labels_from_eval(ev, comps)


def labels_from_eval(ev: pd.DataFrame, incident_components: dict[int, list[str]]) -> pd.DataFrame:
    out = []
    for r in ev.itertuples():
        if pd.notna(r.next_incident_id):
            klass, comps = "pre_incident", incident_components[int(r.next_incident_id)]
        elif bool(r.healthy_start):
            klass, comps = "false_alarm", []
        else:
            klass, comps = "near_incident", []
        out.append({"episode_id": int(r.episode_id), "klass": klass, "incident_components": comps, "incident_id": r.next_incident_id})
    return pd.DataFrame(out)


def score(rows: list[dict], labels: pd.DataFrame) -> dict:
    """Per arm: component accuracy on pre-incident episodes, action appropriateness, per-month curve, cost."""
    lab = labels.set_index("episode_id")
    per = []
    for r in rows:
        lb = lab.loc[r["episode_id"]]
        d = r["diagnosis"] or {}
        comp, action = d.get("component"), d.get("action")
        per.append(
            {
                "episode_id": r["episode_id"],
                "month": r["decision_time"][:7],
                "klass": lb["klass"],
                "component_ok": lb["klass"] == "pre_incident" and comp in lb["incident_components"],
                "detector_component_ok": lb["klass"] == "pre_incident" and r["detector_component"] in lb["incident_components"],
                "action": action,
                "component": comp,
                "appropriate": (lb["klass"] == "pre_incident" and action == "inspect") or (lb["klass"] == "false_alarm" and action == "ignore"),
                "not_inspect_on_fa": lb["klass"] == "false_alarm" and action in ("ignore", "monitor"),
                "error": r["error"] is not None,
                "n_memories": len(r["memories"]),
                "mostly_nothing": bool((r.get("track_record") or {}).get("mostly_nothing", False)),
                "n_memories_outcome_known": sum(m["outcome_known"] for m in r["memories"]),
                "input_tokens": r["usage"]["input_tokens"],
                "output_tokens": r["usage"]["output_tokens"],
                "requests": r["usage"]["requests"],
                "tool_calls": r["usage"]["tool_calls"],
                "seconds": r["seconds"],
            }
        )
    p = pd.DataFrame(per)
    pre, fa, near = (p[p["klass"] == k] for k in ("pre_incident", "false_alarm", "near_incident"))
    actions = lambda df: df["action"].fillna("error").value_counts().to_dict()  # noqa: E731
    monthly = (
        p.groupby("month")
        .agg(
            episodes=("episode_id", "size"),
            pre_incident=("klass", lambda k: int((k == "pre_incident").sum())),
            component_ok=("component_ok", "sum"),
            false_alarm=("klass", lambda k: int((k == "false_alarm").sum())),
            appropriate=("appropriate", "sum"),
            mean_memories=("n_memories", "mean"),
        )
        .reset_index()
    )
    monthly["cum_component_ok"] = monthly["component_ok"].cumsum()
    monthly["cum_pre_incident"] = monthly["pre_incident"].cumsum()
    monthly["cum_appropriate"] = monthly["appropriate"].cumsum()
    monthly["cum_scored"] = (monthly["pre_incident"] + monthly["false_alarm"]).cumsum()
    return {
        "episodes": len(p),
        "errors": int(p["error"].sum()),
        "component_accuracy_pre_incident": f"{int(pre['component_ok'].sum())}/{len(pre)}",
        "detector_only_component_first_day": f"{int(pre['detector_component_ok'].sum())}/{len(pre)}",
        "inspect_on_pre_incident": f"{int((pre['action'] == 'inspect').sum())}/{len(pre)}",
        "ignore_on_false_alarm": f"{int((fa['action'] == 'ignore').sum())}/{len(fa)}",
        "not_inspect_on_false_alarm": f"{int(fa['not_inspect_on_fa'].sum())}/{len(fa)}",
        "appropriate_total": f"{int(p['appropriate'].sum())}/{len(pre) + len(fa)}",
        "actions_pre_incident": actions(pre),
        "actions_false_alarm": actions(fa),
        "actions_near_incident": actions(near),
        "components_pre_incident": pre["component"].fillna("error").value_counts().to_dict(),
        "pre_incident_with_memory": int((pre["n_memories"] > 0).sum()),
        "record_mostly_nothing": {k: int(df["mostly_nothing"].sum()) for k, df in (("pre_incident", pre), ("false_alarm", fa), ("near_incident", near))},
        "inspect_against_record": {
            k: int(((df["action"] == "inspect") & df["mostly_nothing"]).sum()) for k, df in (("pre_incident", pre), ("false_alarm", fa), ("near_incident", near))
        },
        "mean_memories_in_prompt": round(float(p["n_memories"].mean()), 2),
        "mean_memories_with_known_outcome": round(float(p["n_memories_outcome_known"].mean()), 2),
        "cost": {
            "input_tokens": int(p["input_tokens"].sum()),
            "output_tokens": int(p["output_tokens"].sum()),
            "requests": int(p["requests"].sum()),
            "tool_calls": int(p["tool_calls"].sum()),
            "seconds": round(float(p["seconds"].sum()), 1),
            "seconds_per_episode_median": round(float(p["seconds"].median()), 2),
            "input_tokens_per_episode_mean": round(float(p["input_tokens"].mean()), 1),
        },
        "monthly": monthly.to_dict("records"),
        "per_episode": p[["episode_id", "klass", "action", "component_ok", "appropriate", "n_memories"]].to_dict("records"),
    }


# ---------------------------------------------------------------- driver


def read_jsonl(path: Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["episode_id"]: r for r in rows if r.get("error") is None}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=["local", "rule"], default="rule")
    ap.add_argument("--arms", default="none,ungated,gated")
    ap.add_argument("--limit", type=int, default=None, help="only the first N episodes in replay order")
    ap.add_argument("--episodes", default=None, help="comma-separated episode ids (memory still built only from these)")
    ap.add_argument("--output-mode", choices=["tool", "prompted"], default="tool")
    ap.add_argument("--context", choices=["tools", "prefetch"], default="tools")
    ap.add_argument("--tag", default="m3")
    ap.add_argument("--prompt", choices=["v1", "v2"], default="v1", help="v2: costs, track record, justification (PLAN.md)")
    ap.add_argument("--resume", action="store_true", help="reuse diagnoses already in runs/<tag>_<arm>.jsonl")
    args = ap.parse_args(argv)

    from .agent import build_agent, rule_model

    data = ReplayData.load(RUNS_DIR)
    sits = data.situations()
    if args.episodes:
        keep = {int(x) for x in args.episodes.split(",")}
        sits = [s for s in sits if s.episode_id in keep]
    if args.limit:
        sits = sits[: args.limit]
    model = rule_model() if args.model == "rule" else None
    agent = build_agent(model, output_mode=args.output_mode, tools=args.context == "tools", prompt=args.prompt)
    labels = episode_labels()
    RUNS_DIR.mkdir(exist_ok=True)
    summary = {
        "model": args.model,
        "prompt": args.prompt,
        "output_mode": args.output_mode,
        "context": args.context,
        "episodes": [s.episode_id for s in sits],
        "horizon_days": HORIZON_DAYS,
        "policies": {k: (v.__dict__ if v else None) for k, v in ARMS.items()},
        "arms": {},
    }
    for arm in args.arms.split(","):
        path = RUNS_DIR / f"{args.tag}_{arm}.jsonl"
        done = read_jsonl(path) if args.resume else None
        path.unlink(missing_ok=True)  # rewritten row by row; resumed rows are re-emitted from ``done``
        t0 = time.time()
        rows = asyncio.run(
            replay(data, agent, ARMS[arm], arm=arm, situations=sits, prefetch=args.context == "prefetch", log_path=path, done=done, prompt_version=args.prompt)
        )
        s = score(rows, labels)
        s["wall_seconds"] = round(time.time() - t0, 1)
        summary["arms"][arm] = s
        (RUNS_DIR / f"{args.tag}_summary.json").write_text(json.dumps(summary, indent=2, default=str))
        print(
            f"[{arm}] comp {s['component_accuracy_pre_incident']} (detector first day {s['detector_only_component_first_day']}) "
            f"inspect|pre {s['inspect_on_pre_incident']} ignore|FA {s['ignore_on_false_alarm']} appropriate {s['appropriate_total']} "
            f"errors {s['errors']} mem/prompt {s['mean_memories_in_prompt']} tokens in/out {s['cost']['input_tokens']}/{s['cost']['output_tokens']} "
            f"{s['wall_seconds']}s",
            flush=True,
        )


if __name__ == "__main__":
    main()

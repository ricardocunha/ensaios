"""Pure-optimization maintenance baseline: which sections to repair within a
budget. The LLM agents (milestone 3) must match or beat this.

Objective: maximize the sum of ``value`` (condition x criticality x length,
see ``condition.section_table``) subject to sum of ``repair_cost`` <= budget.
Two solvers:

- ``greedy``: sort by value / cost (ties by id), take each section that
  still fits. Simple, explainable, usually near-optimal when items are small
  relative to the budget.
- ``exact``: 0/1 knapsack as a mixed-integer program (SciPy / HiGHS).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass
class Plan:
    method: str
    budget: float
    chosen: list[str]  # ids, in the order chosen (greedy) or by id (exact)
    total_value: float
    total_cost: float


def greedy(ids: Sequence[str], values: Sequence[float], costs: Sequence[float], budget: float) -> Plan:
    ids = list(ids)
    v = np.asarray(values, float)
    c = np.asarray(costs, float)
    ratio = np.where(c > 0, v / np.where(c > 0, c, 1), np.inf)
    order = sorted(range(len(ids)), key=lambda i: (-ratio[i], ids[i]))
    chosen, spent, got = [], 0.0, 0.0
    for i in order:
        if v[i] <= 0:
            continue
        if spent + c[i] <= budget:
            chosen.append(ids[i])
            spent += float(c[i])
            got += float(v[i])
    return Plan("greedy", budget, chosen, got, spent)


def exact(
    ids: Sequence[str],
    values: Sequence[float],
    costs: Sequence[float],
    budget: float,
    time_limit_s: float = 60.0,
) -> Plan:
    from scipy.optimize import Bounds, LinearConstraint, milp

    ids = list(ids)
    v = np.asarray(values, float)
    c = np.asarray(costs, float)
    keep = v > 0
    idx = np.flatnonzero(keep)
    if len(idx) == 0:
        return Plan("exact", budget, [], 0.0, 0.0)
    res = milp(
        c=-v[idx],
        constraints=LinearConstraint(c[idx][None, :], -np.inf, budget),
        integrality=np.ones(len(idx)),
        bounds=Bounds(0, 1),
        options={"time_limit": time_limit_s, "mip_rel_gap": 1e-9},
    )
    if res.x is None:
        raise RuntimeError(f"knapsack solver failed: {res.message}")
    pick = idx[res.x > 0.5]
    chosen = sorted(ids[i] for i in pick)
    method = "exact" if res.status == 0 else f"exact (status {res.status}: {res.message})"
    return Plan(method, budget, chosen, float(v[pick].sum()), float(c[pick].sum()))

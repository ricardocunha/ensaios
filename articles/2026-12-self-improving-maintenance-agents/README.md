# Maintenance agents that learn from their own mistakes

**Status:** drafts complete (EN, EN Medium, PT-BR, LinkedIn EN/PT-BR); numbers final; links pending publication · **Branch:** `article/2026-12-self-improving-maintenance-agents` · **Target date:** 2026-12-11

A case study of a "self-improving" wind-turbine maintenance agent: Pydantic AI with a local Qwen3-8B, episodic memory of past alarms and their logbook outcomes, and a context gate, replayed in time order over 23 months of a real EDP wind farm (CARE to Compare Wind Farm A + EDP failure logbooks, 21 incidents). Three arms (no memory, ungated, gated), with no-look-ahead tests. The agent answered "inspect" to all 77 alarms in every arm; one pre-decided round of fixes (track record, costs, a required justification) left it at "inspect" in 230 of 231 decisions, so memory changed one decision. With 27 of 77 alarms followed by a logged failure and a 1 : 10 cost assumption, always inspecting is close to optimal, and 21 incidents are too few for any statistical claim. The Brazil angle: wind is 14.1 % of Brazil's electricity supply and 92.2 % of wind generation is in the Northeast, but we found no public Brazilian source with turbine-level failure logs. See [PLAN.md](PLAN.md), [code/docs/RESULTS.md](code/docs/RESULTS.md) and [code/docs/DATA.md](code/docs/DATA.md).

| | |
|---|---|
| Article (EN) | [article-en.md](article-en.md) · Medium version: [article-en-medium.md](article-en-medium.md) |
| Article (PT-BR) | [article-pt-br.md](article-pt-br.md) |
| LinkedIn | [EN](linkedin-en.md) · [PT-BR](linkedin-pt-br.md) |
| Code | [code/](code/) |
| Plan | [PLAN.md](PLAN.md) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]

<!-- LinkedIn post (EN), ~1,400 characters. -->

"Self-improving" agents learn from memory. I tested whether that's true on a real wind farm.

I built a maintenance agent (Pydantic AI, an open 8B model running locally) with episodic memory of past alarms and their logbook outcomes, and replayed 23 months of alarms in time order: no memory, memory, memory behind a gate.

What I found:

→ The agent said "inspect" to all 77 alarms, with and without memory. Memory can't fix a decision that never moves.

→ One round of fixes, decided before re-running (track record, costs, a required justification): "inspect" in 230 of 231 decisions. Memory changed exactly one.

→ A required justification is a field, not a check. Once the agent justified inspecting with "higher" readings that its own numbers showed weren't higher.

→ "Always inspect" wasn't dumb here: 27 of 77 alarms preceded a logged failure. At an assumed 1 : 10 cost ratio, that's close to optimal.

And the honest part: 21 incidents can't prove memory helps or hurts. This is a case study of the mechanism, not a learning curve.

In 2024 wind supplied 14.1% of Brazil's electricity, and the Northeast produced 92% of the country's wind generation, but I found no public Brazilian data with turbine-level failure logs. That's what would make this testable.

Full write-up and code: [[LINK]]

#AI #Agents #LLM #PredictiveMaintenance #WindEnergy #Brazil

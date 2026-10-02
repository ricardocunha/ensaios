<!-- LinkedIn post (EN), ~1,300 characters. -->

My agent's checks passed. The answers were still wrong.

I built four agent systems on Brazilian data (public contracts, the 2024 RS floods, Belo Horizonte's roads, wind turbines), each with a deterministic check on the model's output. Every check worked. Every one let wrong answers through:

→ Quotes verified verbatim, used to "refute" the very clause that broke the rule.
→ 98.8% of numbers found in tool outputs (once my own audit bugs were fixed), some attached to the wrong thing ("increased from 54.43% to 48.36%").
→ Every station code in an alert was real; one was given to the wrong town.
→ A required justification, filled in with comparisons that were false by the agent's own numbers.

Each check proved something exists. None proved it was used correctly.

What held up: code decides, the model explains. Bayesian fusion beat the LLM on flood risk (Brier 0.147 vs 0.195). A heuristic finished 9 of 9 schedules; the agent finished 1.

So: check meaning where it's cheap, read the outputs, move decisions into code, and treat a passed check as "escalate less", not "correct".

[[LINK]]

#AI #Agents #LLM #Evaluation #Brazil

<!-- LinkedIn post (EN), ~1,400 characters. -->

An agent that plans road maintenance sounds great until you build the boring baseline next to it.

I built one on Belo Horizonte's real road network (OpenStreetMap) and 198,991 real pothole-repair requests: graph tools in NetworkX, three Pydantic AI agents, an open 8B model on a laptop.

What I found:

→ A greedy knapsack already gets within 1e-5 of the optimal plan. Every change the agent made cost value (it kept 93.8–100%) for at most +1.08 points of request coverage. That's a weight in the objective, not judgment.

→ The agent that schedules road closures finished 1 of 9 runs. 6 of the 8 failures were one id: it wrote "S010128" for "S10128", got "unknown section ids" back, and in 4 of those 6 runs resent the identical call.

→ A small heuristic, no LLM, scheduled every time with zero conflicting closures. The agent's one schedule had a worst month 28.8% worse than the heuristic's.

→ 98.8% of the numbers in the agents' prose traced back to a tool (89.7% on a strict lookup). Some sentences around them were still wrong: "gave up 1.08%" for a gain.

→ Pothole requests measure who reports, not pavement: 21.0 request locations per km on residential streets, 0.10 on the ring motorway.

Build the deterministic baseline first, and make the agent beat it.

Full write-up and code (and every failure): [[LINK]]

#AI #Agents #LLM #OpenStreetMap #UrbanPlanning #OpenData #Brazil

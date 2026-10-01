<!-- LinkedIn post (EN), ~1,300 characters. -->

In May 2024, three of the five river gauges I needed went silent at the crest of the Rio Grande do Sul floods.

I replayed the event hour by hour with a disaster-risk agent (Bayesian fusion of river gauges and rain stations, an open 8B model on a laptop) to see whether it would have warned in time, and what it does when its signals stop reporting.

What I found:

→ My hand-picked likelihood ratios were off by an order of magnitude and never put 4 of 5 places on alert. Fitted on 2019–2022, the fusion alerted 7 to 26 hours before each river reached its flood level, at a cost of 3.23 false alarms per place-year.

→ Silent isn't unknown. Discounting a silent gauge's last reading made calibration worse: the river is usually still high.

→ Let the LLM write, not compute. The agent writes the alert in Portuguese, has no field for the probability, and a deterministic audit checks every number, code and silent gauge. 27 of 27 passed. Reading them still found a code given to the wrong town.

→ Asked to do the fusion itself, the LLM alerted earlier, mostly on hours with no flood in the next 24 h.

A replay, not a warning system: it shows the signals were there, not that anyone missed them.

Full write-up and code: [[LINK]]

#AI #Agents #LLM #Floods #DisasterRisk #Brazil

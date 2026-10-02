<!-- LinkedIn post (EN), ~1,300 characters. -->

A compliance agent that's right 80% of the time is useless if you can't tell which 80%.

I built one for Brazilian public contracts (Docling + MCP + Pydantic AI, an open 8B model on a laptop) and measured when it should hand a case to a human.

What I found:

→ The biggest fixes were in the tools, not the prompt. A search that couldn't match "vincula-se" to "vinculação" caused 10 false alarms; returning the contract's preamble in a tool fixed a jurisdiction error that instructions couldn't.

→ Small models shouldn't do arithmetic on legal limits. Let the model extract the values; let code apply the law. With the search fix: false alarms 34 → 6.

→ The model's confidence said ~0.95 on almost everything.

→ No single escalation signal works everywhere. On clean text, "3 samples disagree" catches 75% of errors. On bad scans the model is consistently wrong (unreadable clause = "missing"), samples agree, and the OCR score is what catches it.

Combined: 99.2% accuracy on what the agent keeps from clean text, and nearly everything escalated from bad scans — which is the right call.

Full write-up and code (and every bug): [[LINK]]

#AI #Agents #LLM #DocumentAI #Compliance #Brazil

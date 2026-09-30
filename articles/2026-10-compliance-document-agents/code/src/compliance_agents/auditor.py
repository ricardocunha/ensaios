"""The auditor: a second agent that tries to refute each violation the reviewer reports.

Most false alarms are "the clause is missing", which comes with no quote to check. So the
auditor doesn't re-read the reviewer's reasoning; it searches the contract itself, and must
back a disagreement with a verbatim quote (checked in code). A disagreement escalates.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from compliance_agents import mcp_server
from compliance_agents.reviewer import mcp_toolset, model_settings, reviewer_model
from compliance_agents.rules import RULES_BY_ID


class Audit(BaseModel):
    agrees: bool = Field(description="true if, after your own search, you also find that the contract violates the rule")
    counter_quote: str = Field(default="", description="If you disagree: a verbatim quote from the contract showing the rule is met")
    reason: str = Field(default="", description="One sentence, in Portuguese")


INSTRUCTIONS = """\
Você é o auditor. Outro revisor afirmou que um contrato viola uma regra da Lei 14.133/2021.
Seu trabalho é tentar REFUTAR essa afirmação: procure no contrato, por conta própria, o trecho que cumpre a regra.
Use search_document com vários termos diferentes (sinônimos, formas verbais) e leia as seções candidatas com get_section.
Só discorde se encontrar uma citação literal que mostre que a regra é cumprida; copie-a em counter_quote.
Se não encontrar, concorde com o revisor.
"""


def make_auditor(toolset) -> Agent[None, Audit]:
    return Agent(reviewer_model(), output_type=Audit, instructions=INSTRUCTIONS, toolsets=[toolset], retries=3,
                 model_settings=model_settings())


def audit_prompt(finding: dict) -> str:
    rule = RULES_BY_ID[finding["rule"]]
    return (
        f"Contrato: {finding['doc']}\nRegra `{rule.id}` ({rule.article}): {rule.check}\n"
        f"Afirmação do revisor: VIOLAÇÃO. Motivo: {finding.get('reason', '')}\n"
        f"Evidência citada: \"{finding.get('evidence', '')}\""
    )


async def audit(auditor: Agent[None, Audit], finding: dict) -> dict:
    out = (await auditor.run(audit_prompt(finding))).output
    quote_ok = bool(out.counter_quote.strip()) and mcp_server.verify_quote(finding["doc"], out.counter_quote)["found"]
    # a disagreement counts only when it comes with a real quote
    return {"doc": finding["doc"], "rule": finding["rule"], "sample": finding.get("sample", 0),
            "auditor_agrees": out.agrees or not quote_ok, "counter_quote": out.counter_quote,
            "counter_quote_verbatim": quote_ok, "auditor_reason": out.reason}


async def amain(args) -> None:
    os.environ["COMPLIANCE_DATA_DIR"] = str(args.data)
    rows = [json.loads(line) for line in args.runs.read_text().splitlines()]
    todo = [r for r in rows if r.get("verdict") == "violation"]
    toolset = mcp_toolset(args.data)
    auditor = make_auditor(toolset)
    async with toolset:
        with args.out.open("w") as f:
            for r in todo:
                try:
                    a = await audit(auditor, r)
                except Exception as e:
                    a = {"doc": r["doc"], "rule": r["rule"], "sample": r.get("sample", 0), "error": f"{type(e).__name__}: {e}"[:300]}
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{r['doc']} {r['rule']:>16} agrees={a.get('auditor_agrees')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path, help="reviewer runs (jsonl)")
    ap.add_argument("--data", type=Path, default=Path("data/synth/text"))
    ap.add_argument("--out", type=Path, required=True)
    asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    main()

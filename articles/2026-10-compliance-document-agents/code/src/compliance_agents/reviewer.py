"""The reviewer: a Pydantic AI agent that checks one rule against one contract.

It reads the contract only through the MCP server (search_document / get_section), and
must quote its evidence verbatim, so the auditor can verify every quote.

Model: $REVIEWER_BASE_URL / $REVIEWER_MODEL (any OpenAI-compatible server). The default is
a local mlx-lm server:  uv run --group local mlx_lm.server --model <qwen3-8b-4bit> --port 8088
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from compliance_agents.rules import RULES, RULES_BY_ID, Rule

Verdict = Literal["compliant", "violation", "not_applicable", "unclear"]


class Finding(BaseModel):
    rule: str
    verdict: Verdict = Field(
        description="compliant: the contract meets the rule; violation: it doesn't (including a required clause that is missing); "
        "not_applicable: the rule doesn't apply to this contract; unclear: the text doesn't let you decide"
    )
    section_id: int | None = Field(description="The section the evidence comes from; null if there is none")
    evidence: str = Field(description="A short verbatim quote from the contract that supports the verdict; empty if the clause is missing")
    confidence: float = Field(ge=0, le=1, description="How sure you are of the verdict, 0 to 1")
    reason: str = Field(description="One or two sentences, in Portuguese")


INSTRUCTIONS = """\
Você revisa contratos administrativos brasileiros quanto a uma regra da Lei 14.133/2021.
Use as ferramentas para ler o contrato: parse_document (sumário), search_document (busca por palavras) e get_section (texto integral).
Regras:
- Baseie o veredito apenas no texto do contrato. Não presuma cláusulas que você não encontrou.
- Antes de concluir que uma cláusula obrigatória está ausente, procure por pelo menos dois termos diferentes e leia o sumário.
- Quando a regra depende de quem é a Administração contratante (por exemplo, a sede para o foro), leia o preâmbulo (seção 0) para identificar o órgão e o município da sua sede.
- A evidência deve ser uma citação literal e curta do contrato (copie, não parafraseie).
- Se o texto estiver ilegível ou ambíguo, use "unclear" e uma confiança baixa.
"""


def reviewer_model() -> OpenAIChatModel:
    load_dotenv()
    provider = OpenAIProvider(
        base_url=os.environ.get("REVIEWER_BASE_URL", "http://localhost:8088/v1"),
        api_key=os.environ.get("REVIEWER_API_KEY", "local"),
    )
    return OpenAIChatModel(os.environ.get("REVIEWER_MODEL", "default_model"), provider=provider)


def mcp_toolset(data_dir: Path) -> MCPToolset:
    transport = StdioTransport(
        command="uv",
        args=["run", "compliance-mcp"],
        env={**os.environ, "COMPLIANCE_DATA_DIR": str(data_dir.resolve())},
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    return MCPToolset(transport)


def model_settings() -> dict:
    settings = {"temperature": 0.7, "max_tokens": 4096}
    if os.environ.get("REVIEWER_THINKING", "0") != "1":
        # Qwen3 thinks by default; on a laptop that is minutes per call. Ignored by APIs that don't know it.
        settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    return settings


def make_agent(toolset: MCPToolset, model=None) -> Agent[None, Finding]:
    return Agent(
        model or reviewer_model(),
        output_type=Finding,
        instructions=INSTRUCTIONS,
        toolsets=[toolset],
        retries=2,
        model_settings=model_settings(),
    )


def rule_prompt(doc_id: str, rule: Rule) -> str:
    return (
        f"Contrato: {doc_id}\n"
        f"Regra `{rule.id}` ({rule.article}): {rule.check}\n"
        f"Texto da lei: \"{rule.law}\"\n"
        f"Responda com o Finding para a regra `{rule.id}`."
    )


async def review(agent: Agent[None, Finding], doc_id: str, rule: Rule) -> dict:
    result = await agent.run(rule_prompt(doc_id, rule))
    finding = result.output.model_copy(update={"rule": rule.id})
    usage = result.usage
    return {
        "doc": doc_id,
        **finding.model_dump(),
        "tool_calls": usage.tool_calls,
        "tokens": (usage.input_tokens or 0) + (usage.output_tokens or 0),
    }


async def amain(args) -> None:
    toolset = mcp_toolset(args.data)
    agent = make_agent(toolset)
    rules = [RULES_BY_ID[r] for r in args.rules] if args.rules else list(RULES)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    async with agent:
        with args.out.open("a") as f:
            for doc_id in args.docs:
                for rule in rules:
                    for sample in range(args.samples):
                        try:
                            row = await review(agent, doc_id, rule)
                        except Exception as e:  # a failed run is data too: record it
                            row = {"doc": doc_id, "rule": rule.id, "error": f"{type(e).__name__}: {e}"[:500]}
                        row["sample"] = sample
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        f.flush()
                        print(f"{doc_id} {rule.id:>16} #{sample} {row.get('verdict', 'ERROR'):>14} {row.get('confidence', '')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("docs", nargs="+")
    ap.add_argument("--rules", nargs="*")
    ap.add_argument("--samples", type=int, default=1, help="runs per (doc, rule); >1 feeds the uncertainty profile")
    ap.add_argument("--data", type=Path, default=Path("data/pncp"))
    ap.add_argument("--out", type=Path, default=Path("runs/review.jsonl"))
    asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    main()

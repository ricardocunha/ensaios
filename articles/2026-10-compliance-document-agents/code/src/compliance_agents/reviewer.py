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

from compliance_agents.limits import EXTRACTORS, HINTS
from compliance_agents.rules import RULES, RULES_BY_ID, Rule

Verdict = Literal["compliant", "violation", "not_applicable", "unclear"]


class Finding(BaseModel):
    rule: str
    verdict: Verdict = Field(
        description="compliant: the contract meets the rule; violation: it doesn't (including a required clause that is missing); "
        "not_applicable: the rule doesn't apply to this contract; unclear: the text doesn't let you decide"
    )
    section_id: int | None = Field(default=None, description="The section the evidence comes from; null if there is none")
    evidence: str = Field(default="", description="A short verbatim quote from the contract that supports the verdict; empty if the clause is missing")
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


def make_agent(toolset: MCPToolset, model=None, output_type=Finding) -> Agent:
    return Agent(
        model or reviewer_model(),
        output_type=output_type,
        instructions=INSTRUCTIONS,
        toolsets=[toolset],
        retries=3,
        model_settings=model_settings(),
    )


def rule_prompt(doc_id: str, rule: Rule) -> str:
    return (
        f"Contrato: {doc_id}\n"
        f"Regra `{rule.id}` ({rule.article}): {rule.check}\n"
        f"Texto da lei: \"{rule.law}\"\n"
        f"Responda com o Finding para a regra `{rule.id}`."
    )


def extract_prompt(doc_id: str, rule: Rule) -> str:
    return (
        f"Contrato: {doc_id}\n"
        f"Extraia do contrato os fatos necessários para a regra `{rule.id}` ({rule.article}). "
        "Não julgue a regra: apenas extraia os valores como estão escritos, com citação literal.\n"
        f"{HINTS.get(rule.id, '')}"
    )


async def review(agent: Agent, doc_id: str, rule: Rule, extractor: Agent | None = None) -> dict:
    """With an extractor (limit rules, --decide code), the model extracts facts and code decides."""
    if extractor is not None:
        result = await extractor.run(extract_prompt(doc_id, rule))
        facts = result.output
        verdict, reason = EXTRACTORS[rule.id][1](facts)
        finding = Finding(rule=rule.id, verdict=verdict, section_id=facts.section_id, evidence=facts.evidence,
                          confidence=facts.confidence, reason=reason)
        extra = {"facts": facts.model_dump()}
    else:
        result = await agent.run(rule_prompt(doc_id, rule))
        finding = result.output.model_copy(update={"rule": rule.id})
        extra = {}
    usage = result.usage
    return {
        "doc": doc_id,
        **finding.model_dump(),
        "tool_calls": usage.tool_calls,
        "tokens": (usage.input_tokens or 0) + (usage.output_tokens or 0),
        **extra,
    }


INFRA_ERRORS = ("ModelAPIError", "Connection", "Timeout")  # the server, not the model


async def redo_errors(args) -> None:
    """Re-run only rows that failed for infrastructure reasons, replacing them in place."""
    rows = [json.loads(line) for line in args.out.read_text().splitlines()]
    toolset = mcp_toolset(args.data)
    agent = make_agent(toolset)
    extractors = {rid: make_agent(toolset, output_type=facts) for rid, (facts, _) in EXTRACTORS.items()} if args.decide == "code" else {}
    async with toolset:
        for i, r in enumerate(rows):
            if not any(k in r.get("error", "") for k in INFRA_ERRORS):
                continue
            rule = RULES_BY_ID[r["rule"]]
            try:
                new = await review(agent, r["doc"], rule, extractors.get(rule.id))
            except Exception as e:
                new = {"doc": r["doc"], "rule": rule.id, "error": f"{type(e).__name__}: {e}"[:500]}
            rows[i] = {**new, "sample": r.get("sample", 0), "decide": args.decide, "redone": True}
            print(f"redo {r['doc']} {rule.id} -> {new.get('verdict', 'ERROR')}")
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


async def amain(args) -> None:
    toolset = mcp_toolset(args.data)
    agent = make_agent(toolset)
    extractors = {rid: make_agent(toolset, output_type=facts) for rid, (facts, _) in EXTRACTORS.items()} if args.decide == "code" else {}
    rules = [RULES_BY_ID[r] for r in args.rules] if args.rules else list(RULES)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    async with toolset:
        with args.out.open("a") as f:
            for doc_id in args.docs:
                for rule in rules:
                    for sample in range(args.samples):
                        try:
                            row = await review(agent, doc_id, rule, extractors.get(rule.id))
                        except Exception as e:  # a failed run is data too: record it
                            row = {"doc": doc_id, "rule": rule.id, "error": f"{type(e).__name__}: {e}"[:500]}
                        row["sample"] = sample
                        row["decide"] = args.decide
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        f.flush()
                        print(f"{doc_id} {rule.id:>16} #{sample} {row.get('verdict', 'ERROR'):>14} {row.get('confidence', '')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("docs", nargs="*")
    ap.add_argument("--rules", nargs="*")
    ap.add_argument("--samples", type=int, default=1, help="runs per (doc, rule); >1 feeds the uncertainty profile")
    ap.add_argument("--data", type=Path, default=Path("data/pncp"))
    ap.add_argument("--out", type=Path, default=Path("runs/review.jsonl"))
    ap.add_argument("--decide", choices=["llm", "code"], default="llm",
                    help="code: for limit rules, the model extracts values and code applies the law")
    ap.add_argument("--redo-errors", action="store_true", help="re-run rows of --out that failed for infrastructure reasons")
    args = ap.parse_args()
    asyncio.run(redo_errors(args) if args.redo_errors else amain(args))


if __name__ == "__main__":
    main()

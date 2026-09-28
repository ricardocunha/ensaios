"""The Extractor: a text-only tool-calling agent, Transcription -> CNH Record | Rejection.

The same graph runs with the Teacher (Claude Sonnet 5) and with the Student
(fine-tuned Qwen3.5-9B behind an OpenAI-compatible endpoint), so their
Trajectories are directly comparable.
"""

from __future__ import annotations

import json
import os

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage

from ..schema import CnhRecord, Rejection
from .tools import TOOLS

SYSTEM_PROMPT = """\
Você extrai dados de CNHs brasileiras a partir de uma transcrição OCR.

A transcrição tem uma linha `RÓTULO: valor` por campo impresso e pode conter erros de OCR \
(O↔0, S↔5, B↔8, acentos perdidos, datas com separadores errados, linhas faltando).

Procedimento:
1. Decida se o texto é de uma CNH. Uma CNH imprime rótulos que só ela tem: CAT. HAB., Nº REGISTRO, \
1ª HABILITAÇÃO, VALIDADE (e PERMISSÃO/ACC). RG, CPF, notas fiscais e outros documentos não têm esses \
rótulos: nesse caso chame `reject_document`. Uma CNH com alguns campos faltando ou ilegíveis continua \
sendo uma CNH: nunca a rejeite por isso.
2. Valide o CPF com `validate_cpf` e o Nº REGISTRO com `validate_cnh_number`. Se falhar, use \
`suggest_ocr_fixes`; só aceite uma correção se houver um único candidato.
3. Normalize datas com `normalize_date` e confira com `check_dates`. Normalize a categoria com \
`normalize_categoria`.
4. Corrija nomes apenas quando o erro de OCR for evidente (ex.: `JOAO` → `JOÃO` não é evidente; \
`J0AO` → `JOAO` é). Nunca invente valores: se a linha de um campo não estiver na transcrição ou \
estiver ilegível, envie esse campo como null.
5. Chame `submit_cnh_record` uma única vez com o registro final.
Depois da resposta ACCEPTED ou REJECTED, responda apenas `OK`."""


BASETEN_MODEL_API = "https://inference.baseten.co/v1"


def teacher_model() -> BaseChatModel:
    """TEACHER_MODEL from .env. Claude models use the Anthropic API; anything else is an
    open-weight model on Baseten's OpenAI-compatible Model APIs (the Teacher must be a model
    whose license allows training on its outputs; see docs/SMITHTUNE_NOTES.md)."""
    name = os.getenv("TEACHER_MODEL", "deepseek-ai/DeepSeek-V4-Pro-0813")
    if name.startswith("claude"):
        from langchain_anthropic import ChatAnthropic

        # Sonnet 5: no temperature (rejected); thinking is adaptive; effort controls depth.
        return ChatAnthropic(model=name, max_tokens=16000, thinking={"type": "adaptive"},
                             output_config={"effort": "medium"})
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=name, base_url=BASETEN_MODEL_API, api_key=os.environ["BASETEN_API_KEY"],
                      temperature=0, max_tokens=8000, stream_usage=True)


def student_model(base_url: str, model: str, api_key: str | None = None) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(base_url=base_url, model=model, api_key=api_key or os.getenv("BASETEN_API_KEY"),
                      temperature=0)


def build_extractor(model: BaseChatModel):
    middleware = []
    if type(model).__name__ == "ChatAnthropic":
        # Each run resends the system prompt, 8 tool definitions and a growing history 7-9 times.
        # Cache the system prompt, tools and conversation tail (Sonnet 5's minimum is 1,024 tokens).
        from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

        middleware.append(AnthropicPromptCachingMiddleware(ttl="5m"))
    return create_agent(model, TOOLS, system_prompt=SYSTEM_PROMPT, middleware=middleware, name="cnh-extractor")


def final_outcome(messages) -> CnhRecord | Rejection | None:
    """The agent's last *effective* decision: an accepted submit, or a reject."""
    accepted = {m.tool_call_id for m in messages
                if isinstance(m, ToolMessage) and str(m.content).startswith("ACCEPTED")}
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            for call in reversed(msg.tool_calls):
                if call["name"] == "submit_cnh_record" and call["id"] in accepted:
                    try:
                        return CnhRecord(**call["args"])
                    except ValueError:
                        return None
                if call["name"] == "reject_document":
                    return Rejection(**call["args"])
    return None


def user_message(transcription: str) -> dict:
    return {"role": "user", "content": f"Transcrição:\n\n{transcription}"}


def outcome_json(outcome: CnhRecord | Rejection | None) -> str:
    return "null" if outcome is None else json.dumps(outcome.model_dump(), ensure_ascii=False)

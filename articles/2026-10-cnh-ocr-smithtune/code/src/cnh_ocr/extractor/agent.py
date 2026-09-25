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
from langchain_core.messages import AIMessage

from ..schema import CnhRecord, Rejection
from .tools import TOOLS

SYSTEM_PROMPT = """\
Você extrai dados de CNHs brasileiras a partir de uma transcrição OCR.

A transcrição tem uma linha `RÓTULO: valor` por campo impresso e pode conter erros de OCR \
(O↔0, S↔5, B↔8, acentos perdidos, datas com separadores errados, linhas faltando).

Procedimento:
1. Se o texto não for de uma CNH (RG, nota fiscal, outro documento), chame `reject_document`.
2. Valide o CPF com `validate_cpf` e o Nº REGISTRO com `validate_cnh_number`. Se falhar, use \
`suggest_ocr_fixes`; só aceite uma correção se houver um único candidato.
3. Normalize datas com `normalize_date` e confira com `check_dates`. Normalize a categoria com \
`normalize_categoria`.
4. Corrija nomes apenas quando o erro de OCR for evidente (ex.: `JOAO` → `JOÃO` não é evidente; \
`J0AO` → `JOAO` é). Nunca invente campos ausentes: use null quando o campo opcional não existir.
5. Chame `submit_cnh_record` uma única vez com o registro final. `formato` é `digital` se a \
transcrição indicar CNH Digital, senão `fisica`.
Depois da resposta ACCEPTED ou REJECTED, responda apenas `OK`."""


def teacher_model() -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    # Sonnet 5: no temperature (rejected); thinking is adaptive; effort controls depth.
    return ChatAnthropic(model=os.getenv("TEACHER_MODEL", "claude-sonnet-5"), max_tokens=16000,
                         thinking={"type": "adaptive"}, output_config={"effort": "medium"})


def student_model(base_url: str, model: str, api_key: str | None = None) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(base_url=base_url, model=model, api_key=api_key or os.getenv("BASETEN_API_KEY"),
                      temperature=0)


def build_extractor(model: BaseChatModel):
    return create_agent(model, TOOLS, system_prompt=SYSTEM_PROMPT, name="cnh-extractor")


def final_outcome(messages) -> CnhRecord | Rejection | None:
    """The last submit/reject call the agent made, parsed into the domain type."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            for call in reversed(msg.tool_calls):
                if call["name"] == "submit_cnh_record":
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

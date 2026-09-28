"""The full Extractor graph with a scripted model: no API calls, checks the wiring."""

import random
from datetime import date

from faker import Faker
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from cnh_ocr import transcription as tx
from cnh_ocr.evaluation.metrics import score_record
from cnh_ocr.extractor.agent import build_extractor, final_outcome, user_message
from cnh_ocr.schema import Rejection
from cnh_ocr.synth.records import random_record


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _record():
    fake = Faker("pt_BR")
    fake.seed_instance(1)
    return random_record(random.Random(1), fake, date(2026, 9, 25))


def test_submit_flow_produces_exact_record():
    rec = _record()
    model = ScriptedModel(responses=[
        AIMessage("", tool_calls=[{"name": "validate_cpf", "args": {"cpf": rec.cpf}, "id": "1"}]),
        AIMessage("", tool_calls=[{"name": "submit_cnh_record", "args": rec.model_dump(), "id": "2"}]),
        AIMessage("OK"),
    ])
    result = build_extractor(model).invoke({"messages": [user_message(tx.from_record(rec))]})
    outcome = final_outcome(result["messages"])
    assert outcome.model_dump() == rec.model_dump()  # formato is excluded: not the Extractor's job
    assert score_record(outcome, rec).exact
    assert "ACCEPTED" in result["messages"][-2].content


def test_reject_flow_scores_correct_for_non_cnh():
    model = ScriptedModel(responses=[
        AIMessage("", tool_calls=[{"name": "reject_document", "args": {"motivo": "é um RG"}, "id": "1"}]),
        AIMessage("OK"),
    ])
    result = build_extractor(model).invoke({"messages": [user_message("REGISTRO GERAL: 12.345.678-9")]})
    outcome = final_outcome(result["messages"])
    assert isinstance(outcome, Rejection)
    assert score_record(outcome, None).exact

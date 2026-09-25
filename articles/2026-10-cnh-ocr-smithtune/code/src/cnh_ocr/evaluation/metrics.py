"""Scoring against ground truth. Field-level exact match is the headline metric (Q19)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import transcription as tx
from ..schema import FIELD_NAMES, CnhRecord, Rejection


_TAGS = re.compile(r"<[^>]+>")


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(pred: str, truth: str) -> float:
    return levenshtein(pred, truth) / max(1, len(truth))


def _norm(v) -> str:
    if isinstance(v, list):
        return " / ".join(_norm(x) for x in v)
    return " ".join(str(v or "").upper().split())


@dataclass
class Score:
    correct_outcome: bool  # right CNH-vs-Non-CNH decision
    fields: dict[str, bool] = field(default_factory=dict)

    @property
    def field_accuracy(self) -> float:
        return sum(self.fields.values()) / len(self.fields) if self.fields else float(self.correct_outcome)

    @property
    def exact(self) -> bool:
        return self.correct_outcome and all(self.fields.values())


def score_record(pred: CnhRecord | Rejection | None, truth: CnhRecord | None) -> Score:
    """`truth=None` means the input was a Non-CNH and should be Rejected."""
    if truth is None:
        return Score(correct_outcome=isinstance(pred, Rejection))
    if not isinstance(pred, CnhRecord):
        return Score(correct_outcome=False, fields={f: False for f in FIELD_NAMES})
    p, t = pred.model_dump(), truth.model_dump()
    return Score(correct_outcome=True, fields={f: _norm(p[f]) == _norm(t[f]) for f in FIELD_NAMES})


def score_transcription(pred: str, truth: str) -> dict:
    """Reader metrics: per-label exact match plus overall CER."""
    if truth == tx.NOT_A_CNH:
        ok = float(tx.NOT_A_CNH in pred.upper())
        return {"label_accuracy": ok, "value_recall": ok, "cer": cer(pred, truth), "labels": {}}
    p, t = tx.parse(pred), tx.parse(truth)
    # Score only the labels the ground truth has. Synthetic truth has all 14; BID's
    # CNH_Frente shows fewer. " / " splits (Filiação lines) don't count as errors.
    same = lambda a, b: _norm(a).replace(" / ", " ") == _norm(b).replace(" / ", " ")
    labels = {label: same(p.get(label), t[label]) for label in t}
    # Format-agnostic: is each printed value somewhere in the output? Separates
    # "can't read it" from "can't follow the LABEL: value contract".
    haystack = _norm(_TAGS.sub(" ", pred))  # Chandra emits HTML layout zero-shot
    printed = [v for label in tx.LABELS for v in _norm(t.get(label)).split(" / ") if v]
    recall = sum(v in haystack for v in printed) / max(1, len(printed))
    return {"label_accuracy": sum(labels.values()) / len(labels), "value_recall": recall,
            "cer": cer(pred, truth), "labels": labels}

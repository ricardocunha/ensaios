"""Vision-language diagnosis with typed output.

The model sees one fundus photo (plus retrieved cases, for the retrieval arm) and must
answer with JSON that validates against `Diagnosis`. An invalid answer is retried with
the validation error appended (greedy decoding would repeat a plain retry).

Research demo, not a medical device.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from eye_rag.labels import BY_CODE, CODES, NORMAL_DESCRIPTION

NORMAL_LABEL = "normal"
ALLOWED = (*CODES, NORMAL_LABEL)
Label = Literal[ALLOWED]  # type: ignore[valid-type]

MODEL_ID = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
MODEL_REVISION = "defcdea7cc7a4b0858fea563cbbce171d328e457"


class Diagnosis(BaseModel):
    """What the model must return. `cited_cases` is only meaningful with retrieval."""

    model_config = ConfigDict(extra="forbid")

    labels: list[Label] = Field(min_length=1)
    cited_cases: list[int] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=600)

    @field_validator("labels", mode="before")
    @classmethod
    def _normalise(cls, v):
        # accept "dr" or "Normal"; the vocabulary itself is still enforced by Literal
        if isinstance(v, list):
            out = []
            for x in v:
                if isinstance(x, str):
                    s = x.strip()
                    out.append(NORMAL_LABEL if s.lower() == NORMAL_LABEL else s.upper())
                else:
                    out.append(x)
            return list(dict.fromkeys(out))
        return v

    @model_validator(mode="after")
    def _normal_is_exclusive(self):
        if NORMAL_LABEL in self.labels and len(self.labels) > 1:
            raise ValueError('"normal" cannot be combined with a condition')
        return self


# --------------------------------------------------------------------------- prompt


def label_menu() -> str:
    lines = [f"- {c}: {BY_CODE[c].name} ({BY_CODE[c].description})" for c in CODES]
    lines.append(f"- {NORMAL_LABEL}: {NORMAL_DESCRIPTION} (use alone)")
    return "\n".join(lines)


INSTRUCTIONS = """You are assisting a research study on retinal fundus photographs (not clinical use).
Look at the QUERY fundus photograph and list every finding you can see, using ONLY these label codes:
{menu}

Rules:
- A photo can have several findings; list all that apply.
- If no finding is visible, answer ["normal"] and nothing else.
{case_rules}Answer with a single JSON object and nothing else, in this form:
{{"labels": ["CODE", ...], "cited_cases": [{cite_hint}], "rationale": "one or two sentences on what you see"}}"""

CASE_RULES = """- You are also shown {k} reference cases: photographs from a labelled archive that look similar to the query, each with the findings recorded for it. They are examples, not the answer: the query can differ from all of them.
- In "cited_cases", list the numbers of the reference cases that informed your answer (empty if none).
"""


def case_report(labels: Sequence[str]) -> str:
    """The text 'report' of a labelled case (RFMiD has no free text; this is built from labels)."""
    if not labels or list(labels) == ["NORMAL"]:
        return f"normal fundus: {NORMAL_DESCRIPTION}."
    return "; ".join(f"{BY_CODE[c].name} ({c}): {BY_CODE[c].description}" for c in sorted(labels)) + "."


@dataclass(frozen=True)
class Case:
    path: Path
    labels: tuple[str, ...]


def build_parts(query: Path, cases: Sequence[Case] = ()) -> list[str | Path]:
    """The fixed prompt as interleaved text and images."""
    head = INSTRUCTIONS.format(
        menu=label_menu(),
        case_rules=CASE_RULES.format(k=len(cases)) if cases else "",
        cite_hint="case numbers" if cases else "",
    )
    parts: list[str | Path] = [head]
    for i, c in enumerate(cases, 1):
        parts += [f"\nReference case {i}. Recorded findings: {case_report(c.labels)}", c.path]
    parts += ["\nQUERY photograph:", query, "\nJSON answer:"]
    return parts


# --------------------------------------------------------------------------- parsing + retries


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> str:
    """The JSON object in a model answer (strips code fences and surrounding prose)."""
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the answer")
    return text[start : end + 1]


def parse_diagnosis(text: str) -> Diagnosis:
    return Diagnosis.model_validate(json.loads(extract_json(text)))


class VisionModel(Protocol):
    name: str

    def generate(self, parts: Sequence[str | Path], max_tokens: int) -> str: ...


@dataclass
class Outcome:
    diagnosis: Diagnosis | None
    attempts: int
    raw: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0


def diagnose(model: VisionModel, query: Path, cases: Sequence[Case] = (), retries: int = 2, max_tokens: int = 200) -> Outcome:
    """Ask the model; on invalid JSON / labels, retry with the error message (up to `retries` times)."""
    parts = build_parts(query, cases)
    out = Outcome(None, 0)
    t = time.perf_counter()
    for attempt in range(retries + 1):
        out.attempts = attempt + 1
        p = parts if attempt == 0 else [*parts[:-1], f"\nYour previous answer was invalid ({out.errors[-1]}). Use only the listed codes and reply with the JSON object only.\nJSON answer:"]
        text = model.generate(p, max_tokens)
        out.raw.append(text)
        try:
            out.diagnosis = parse_diagnosis(text)
            break
        except (ValueError, ValidationError) as e:  # json.JSONDecodeError is a ValueError
            out.errors.append(_short_error(e))
    out.seconds = time.perf_counter() - t
    return out


def _short_error(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:3])[:300]
    return str(e)[:300]


# --------------------------------------------------------------------------- mlx-vlm backend


class MlxVlm:
    """A local VLM through mlx-vlm (Apple Silicon). Images are resized so the long side
    is `query_side` (the last image, the query) or `case_side` (reference cases)."""

    def __init__(self, model_id: str = MODEL_ID, revision: str = MODEL_REVISION, query_side: int = 768, case_side: int = 448):
        from huggingface_hub import snapshot_download
        from mlx_vlm import load

        path = snapshot_download(model_id, revision=revision)
        self.model, self.processor = load(path)
        self.name = f"{model_id}@{revision[:8]}"
        self.query_side, self.case_side = query_side, case_side

    def _image(self, p: Path, side: int):
        from PIL import Image

        from eye_rag.dedup import fundus_crop

        im = fundus_crop(Image.open(p).convert("RGB"))
        im.thumbnail((side, side), Image.Resampling.LANCZOS)
        return im

    def generate(self, parts: Sequence[str | Path], max_tokens: int) -> str:
        from mlx_vlm import generate

        paths = [x for x in parts if isinstance(x, Path)]
        content = [{"type": "image"} if isinstance(x, Path) else {"type": "text", "text": x} for x in parts]
        prompt = self.processor.apply_chat_template([{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)
        images = [self._image(p, self.query_side if i == len(paths) - 1 else self.case_side) for i, p in enumerate(paths)]
        r = generate(self.model, self.processor, prompt, image=images, max_tokens=max_tokens, temperature=0.0, verbose=False)
        return r.text if hasattr(r, "text") else str(r)

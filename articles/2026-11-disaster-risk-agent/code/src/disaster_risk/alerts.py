"""The alert agent: an LLM writes the alert text; the numbers come from fusion.

``probability`` and ``level`` come from the fused state (the agent has no output field for them);
:func:`citation_audit` then checks every number, station code, place name, silent gauge and risk level
in the text against the input block. Default language is pt-BR with decimal commas (``lang="en"``
reproduces the milestone 3 run). Model: ``$ALERT_BASE_URL`` / ``$ALERT_MODEL``, by default the local
mlx-lm server with Qwen3 thinking off.

``uv run python -m disaster_risk.alerts --limit N`` runs the agent on the key
hours of ``runs/m3/key_hours.json`` (written by ``evaluate``) and appends one
JSON line per alert to ``runs/m3/alerts.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext, ToolOutput

from . import basin
from .backtest import RUNS_DIR
from .fusion import LEVELS, FusedState, sigmoid

OUT_DIR = RUNS_DIR / "m3"
LEVEL_NAMES = tuple(name for name, _ in LEVELS)
SOURCE_LABEL = {"ana_level": "river level (ANA)", "ana_rain": "rain gauge (ANA)", "inmet_rain": "rain station (INMET)"}
Lang = Literal["en", "pt"]
DEFAULT_LANG: Lang = "pt"

# pt-BR labels for the input block (the model copies its wording and number format).
PT = {
    "source": {"ana_level": "nível do rio (ANA)", "ana_rain": "pluviômetro (ANA)", "inmet_rain": "estação de chuva (INMET)"},
    "role": {"gauge": "régua do local", "upstream": "montante/vizinha", "rain": "chuva"},
    "status": {"fresh": "atual", "stale": "desatualizada", "missing": "ausente"},
    "level": {"normal": "NORMAL", "attention": "ATENÇÃO", "alert": "ALERTA", "emergency": "EMERGÊNCIA"},
}


# --- input block ---------------------------------------------------------------------


@dataclass(frozen=True)
class AlertInput:
    """Everything the model sees, rendered once; the audit checks the text against ``text``."""

    place: str
    time_local: str
    probability: float
    level: str
    text: str
    stations: frozenset[str]  # station codes in the input
    places: frozenset[str]  # place names in the input
    silent: dict[str, str] = field(default_factory=dict)  # station code -> its place name
    lang: Lang = "en"


def _pct(p: float, lang: Lang = "en") -> str:
    out = f"{100 * p:.1f}%"
    return out.replace(".", ",") if lang == "pt" else out


def _num(x: float | None, nd: int = 1, lang: Lang = "en") -> str:
    if x is None:
        return "n/a"
    out = f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{x:.0f}"
    return out.replace(".", ",") if lang == "pt" else out


def build_input(state: FusedState | dict, lang: Lang = DEFAULT_LANG) -> AlertInput:
    """Render a fused state (object or ``evaluate.state_json`` dict) into the model's input block."""
    s = state if isinstance(state, dict) else _state_dict(state)
    if lang == "pt":
        return _build_input_pt(s)
    contribs = sorted(s["contributions"], key=lambda c: -abs(c["log_odds"]))
    total = s["log_odds"]
    t_local = s.get("t_local") or s["t"]
    lines = [
        f"Place: {s['place']}",
        f"Time: {t_local} local (UTC-3)",
        f"Hypothesis: the {s['place']} river gauge reaches its official flood level within the next 24 hours.",
        f"Prior (from 2019-2022 history): {_pct(s['prior'])}",
        f"Fused probability: {_pct(s['probability'])} -> risk level: {s['level'].upper()}",
        "Risk levels: normal < 10% <= attention < 50% <= alert < 90% <= emergency.",
        "",
        "Signals, largest effect first. 'effect' is the change in log-odds; 'without it' is the probability if this signal were removed:",
    ]
    stations, places = set(), {s["place"]}
    for c in contribs:
        stations.add(c["station"])
        if c["station_place"]:
            places.add(c["station_place"])
        without = sigmoid(total - c["log_odds"])
        if c["value"] is None:
            val = "no reading"
        elif c["unit"] == "cm":
            val = f"{_num(c['value'], 0)} cm ({_num(c['value'] / 100, 2)} m)"
        else:
            val = f"{_num(c['value'])} {c['unit']}"
        age = "no reading in 72 h" if c["freshness_h"] is None else f"reading {_num(c['freshness_h'])} h old"
        lines.append(
            f"- {SOURCE_LABEL.get(c['source'], c['source'])} {c['station']} at {c['station_place']} "
            f"[{c['role']}]: {val}; {c['status']}, {age}; LR {_num(c['likelihood_ratio'], 2)}, "
            f"reliability {_num(c['reliability'], 2)}; effect {c['log_odds']:+.2f}; without it {_pct(without)}"
        )
    silent = {}
    code_place = {c["station"]: c["station_place"] for c in contribs}
    if s["silent_gauges"]:
        lines += ["", "Silent river gauges (no fresh reading; their last value is used with reduced reliability, or not at all):"]
        for code in s["silent_gauges"]:
            # ANA rain shares the station code: the silent gauge is the *level* signal.
            c = next(c for c in contribs if c["station"] == code and c["source"] == "ana_level")
            silent[code] = code_place.get(code, "")
            last = "none in 72 h" if c["value"] is None else f"{_num(c['value'], 0)} cm"
            age = "over 72 h" if c["freshness_h"] is None else f"{_num(c['freshness_h'])} h"
            lines.append(f"- {code} at {code_place.get(code, '')}: last reading {last}, {age} ago")
    else:
        lines += ["", "Silent river gauges: none."]
    return AlertInput(s["place"], t_local, s["probability"], s["level"], "\n".join(lines),
                      frozenset(stations), frozenset(places), silent, "en")


def _build_input_pt(s: dict) -> AlertInput:
    """The same input block in pt-BR (decimal commas), for the Portuguese alert agent."""
    contribs = sorted(s["contributions"], key=lambda c: -abs(c["log_odds"]))
    total = s["log_odds"]
    t_local = s.get("t_local") or s["t"]
    lines = [
        f"Local: {s['place']}",
        f"Hora: {t_local} (hora local, UTC-3)",
        f"Hipótese: a régua de {s['place']} atinge a cota de inundação oficial nas próximas 24 horas.",
        f"Probabilidade a priori (histórico 2019-2022): {_pct(s['prior'], 'pt')}",
        f"Probabilidade combinada: {_pct(s['probability'], 'pt')} -> nível de risco: {PT['level'][s['level']]}",
        "Níveis de risco: normal < 10% <= atenção < 50% <= alerta < 90% <= emergência.",
        "",
        ("Sinais, do maior efeito para o menor. 'efeito' é a variação em log-odds; 'sem ele' é a probabilidade "
         "se este sinal fosse removido:"),
    ]
    stations, places = set(), {s["place"]}
    for c in contribs:
        stations.add(c["station"])
        if c["station_place"]:
            places.add(c["station_place"])
        without = sigmoid(total - c["log_odds"])
        if c["value"] is None:
            val = "sem leitura"
        elif c["unit"] == "cm":
            val = f"{_num(c['value'], 0, 'pt')} cm ({_num(c['value'] / 100, 2, 'pt')} m)"
        else:
            val = f"{_num(c['value'], 1, 'pt')} {c['unit']}"
        age = ("sem leitura em 72 h" if c["freshness_h"] is None
               else f"leitura de {_num(c['freshness_h'], 1, 'pt')} h atrás")
        effect = f"{c['log_odds']:+.2f}".replace(".", ",")
        lines.append(
            f"- {PT['source'].get(c['source'], c['source'])} {c['station']} em {c['station_place']} "
            f"[{PT['role'].get(c['role'], c['role'])}]: {val}; {PT['status'].get(c['status'], c['status'])}, {age}; "
            f"RV {_num(c['likelihood_ratio'], 2, 'pt')}, confiabilidade {_num(c['reliability'], 2, 'pt')}; "
            f"efeito {effect}; sem ele {_pct(without, 'pt')}"
        )
    silent = {}
    code_place = {c["station"]: c["station_place"] for c in contribs}
    if s["silent_gauges"]:
        lines += ["", ("Réguas silenciosas (sem leitura recente; o último valor é usado com confiabilidade "
                       "reduzida, ou não é usado):")]
        for code in s["silent_gauges"]:
            c = next(c for c in contribs if c["station"] == code and c["source"] == "ana_level")
            silent[code] = code_place.get(code, "")
            last = "nenhuma em 72 h" if c["value"] is None else f"{_num(c['value'], 0, 'pt')} cm"
            age = "mais de 72 h" if c["freshness_h"] is None else f"{_num(c['freshness_h'], 1, 'pt')} h"
            lines.append(f"- {code} em {code_place.get(code, '')}: última leitura {last}, há {age}")
    else:
        lines += ["", "Réguas silenciosas: nenhuma."]
    return AlertInput(s["place"], t_local, s["probability"], s["level"], "\n".join(lines),
                      frozenset(stations), frozenset(places), silent, "pt")


def _state_dict(f: FusedState) -> dict:
    from dataclasses import asdict

    d = asdict(f)
    d["t_local"] = f"{f.t + basin.ANA_UTC_OFFSET:%Y-%m-%d %H:%M}"
    return d


# --- output ------------------------------------------------------------------------------


class Driver(BaseModel):
    station: str = Field(description="Station code exactly as in the input, e.g. 86510000 or A840")
    effect: Literal["raises", "lowers"] = Field(description="Whether this signal raises or lowers the risk")


class AlertDraft(BaseModel):
    headline: str = Field(description="One line for the public, max 120 characters, names the place and the risk level")
    explanation: str = Field(
        description="2 to 5 sentences: which signals moved the estimate and by how much (use the effect and "
        "'without it' numbers from the input), and which gauges are silent"
    )
    drivers: list[Driver] = Field(description="The 1 to 4 signals that moved the estimate most")
    silent_gauges: list[str] = Field(description="Station codes of every silent river gauge listed in the input; empty if none")


class Audit(BaseModel):
    ok: bool
    numbers_checked: int
    ungrounded_numbers: list[str]
    unknown_stations: list[str]
    unknown_places: list[str]
    silent_not_mentioned: list[str]
    silent_field_mismatch: list[str]
    wrong_level: list[str]


class Alert(BaseModel):
    place: str
    time_local: str
    probability: float  # from fusion, never from the model
    level: str  # from fusion, never from the model
    headline: str
    explanation: str
    drivers: list[Driver]
    silent_gauges: list[str]
    audit: Audit


# --- citation audit ----------------------------------------------------------------------

_CODE_RE = re.compile(r"\b(?:\d{8}|A\d{3})\b")
# A number is either thousands-grouped ("1.355", "1,355", "1.355,5") or plain with at most one separator
# ("3,66", "3.66", "1355"). Which separator is decimal is decided per token in _candidates.
_NUM_RE = re.compile(r"(?<![\w.,])[-+]?(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?(?![\d])|\d+(?:[.,]\d+)?)")
_LEVEL_RE = re.compile(r"\b(normal|attention|alert|emergency)\b[\s-]*(?:level|risk)|(?:level|risk)(?: level)?(?: is| of|:)?\s+(normal|attention|alert|emergency)\b", re.I)
# pt-BR: "nível de risco: EMERGÊNCIA", "risco de emergência", "nível de alerta", "risco ALERTA".
_LEVEL_PT_RE = re.compile(r"\b(?:n[ií]vel|risco)(?:\s+de\s+risco)?(?:\s+(?:é|de|em))?\s*:?\s*"
                          r"(normal|aten[cç][aã]o|alerta|emerg[eê]ncia)\b", re.I)
_LEVEL_PT = {"normal": "normal", "atencao": "attention", "alerta": "alert", "emergencia": "emergency"}


def known_places() -> set[str]:
    from .fusion import PLACES

    names = set(basin.STATION_PLACE.values()) | set(PLACES) | {n for n, _ in basin.ANA_STATIONS.values()}
    names |= set(basin.INMET_STATIONS.values())
    return {n for n in names if n}


# "Taquari" and "Guaíba" are also a river, a valley and a lake: those uses are not place citations.
_WATER_RE = re.compile(r"\b(?:rio|river|valley|vale|lake|lago|basin|bacia)\s+(?:do\s+|of\s+the\s+)?(?:taquari|gua[ií]ba)\b"
                       r"|\b(?:taquari|gua[ií]ba)(?:-antas)?\s+(?:river|valley|basin|lake)\b", re.I)


_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n")
_SILENT_RE = re.compile(r"silent|stale|no (?:fresh |new |recent )?(?:reading|data)|not reporting|stopped reporting|offline|gone quiet"
                        # pt-BR
                        r"|silenci|em sil[eê]ncio|sem (?:nova |novas |nenhuma )?(?:leitura|dado|transmiss|medi)"
                        r"|desatualizad|n[aã]o (?:est[aá] )?(?:reporta|envia|transmit|registra)"
                        r"|parou de (?:reportar|enviar|transmitir|medir|registrar)|fora do ar|sem comunica", re.I)


def _numbers(text: str) -> list[str]:
    return _NUM_RE.findall(_CODE_RE.sub(" ", text))


def _candidates(tok: str) -> list[tuple[float, int]]:
    """Every reading of a number token as (value, decimals), in English or Brazilian format.

    "1.355" is 1.355 *or* 1355 (a thousands group); the audit accepts a token if any reading is grounded.
    """
    t = tok.lstrip("+-")
    out = []
    m = re.fullmatch(r"(\d{1,3}(?:([.,])\d{3})+)(?:([.,])(\d+))?", t)
    if m and m.group(3) != m.group(2):  # thousands group, optionally with the other separator as decimal
        whole = m.group(1).replace(m.group(2), "")
        dec = m.group(4) or ""
        out.append((float(f"{whole}.{dec}" if dec else whole), len(dec)))
    if t.count(".") + t.count(",") <= 1:
        dec = re.split(r"[.,]", t)[1] if re.search(r"[.,]", t) else ""
        out.append((float(t.replace(",", ".")), len(dec)))
    return out


def _value(tok: str) -> list[float]:
    return [abs(v) for v, _ in _candidates(tok)]


def _grounded(tok: str, allowed: list[float]) -> bool:
    return any(abs(x - a) <= 0.5 * 10 ** -d + 1e-9 for x, d in _candidates(tok) for a in allowed)


def _strip_accents(w: str) -> str:
    return w.lower().translate(str.maketrans("áâãàéêíóôõúç", "aaaaeeiooouc"))


def stated_levels(headline: str, explanation: str) -> set[str]:
    """Risk levels the text states, as internal names (EN and pt-BR wording)."""
    text = f"{headline}\n{explanation}"
    levels = {(a or b).lower() for a, b in _LEVEL_RE.findall(text)}
    levels |= {_LEVEL_PT[_strip_accents(w)] for w in _LEVEL_PT_RE.findall(text)}
    # In the headline any level word but the generic "alert"/"alerta" counts as the stated level. pt "Atenção" is
    # left out too: it is also an interjection ("Atenção: ..."); "nível de atenção" is caught above.
    levels |= {w.lower() for w in re.findall(r"\b(normal|attention|emergency)\b", headline, re.I)}
    levels |= {_LEVEL_PT[_strip_accents(w)] for w in re.findall(r"\b(emerg[eê]ncia)\b", headline, re.I)}
    return levels


def citation_audit(inp: AlertInput, draft: AlertDraft) -> Audit:
    text = f"{draft.headline}\n{draft.explanation}"
    allowed = [v for t in _numbers(inp.text) for v in _value(t)]
    nums = _numbers(text)
    ungrounded = [t for t in nums if not _grounded(t, allowed)]
    codes = set(_CODE_RE.findall(text)) | {d.station for d in draft.drivers}
    unknown_codes = sorted(c for c in codes if c not in inp.stations)
    plain = _WATER_RE.sub(" ", text).lower()
    unknown_places = sorted(p for p in known_places() if p not in inp.places and p.lower() in plain
                            and not any(p.lower() in q.lower() for q in inp.places))
    sentences = [x.lower() for x in _SENTENCE_RE.split(text)]
    missing_silent = [c for c, pl in inp.silent.items() if c not in text and not any(
        pl and pl.lower() in x and _SILENT_RE.search(x) for x in sentences)]
    field_mismatch = sorted(set(draft.silent_gauges) ^ set(inp.silent))
    wrong = sorted(lv for lv in stated_levels(draft.headline, draft.explanation) if lv != inp.level)
    ok = not (ungrounded or unknown_codes or unknown_places or missing_silent or field_mismatch or wrong)
    return Audit(ok=ok, numbers_checked=len(nums), ungrounded_numbers=ungrounded, unknown_stations=unknown_codes,
                 unknown_places=unknown_places, silent_not_mentioned=missing_silent,
                 silent_field_mismatch=field_mismatch, wrong_level=wrong)


# --- agent ---------------------------------------------------------------------------------

INSTRUCTIONS = """\
You write flood alerts for civil-defence staff in the Taquari valley and Porto Alegre (Rio Grande do Sul, Brazil).
A fusion model has already computed the flood probability and the risk level from river gauges and rain stations.
Those numbers are final: repeat them exactly, never recompute, round differently or change them.

Write:
- headline: the place, the risk level and the probability.
- explanation: 2 to 5 sentences. Say which signals moved the estimate most and by how much, using only the
  'effect' and 'without it' numbers and the readings given in the input. Mention signals that lower the risk if they matter.
  If any river gauge is silent, say so explicitly, with its station code and how long it has been silent,
  and say that its last reading is being trusted less (or not at all).
- drivers: the 1 to 4 signals with the largest effect.
- silent_gauges: the station codes of every silent gauge in the input (empty list if none).

Rules: use only numbers, station codes and place names that appear in the input. Do not add forecasts, river heights,
times or places that are not in the input. Answer in English.
"""

# The pt-BR agent (default): same content, for Brazilian civil defence. Field names stay in English (schema).
INSTRUCTIONS_PT = """\
Você escreve alertas de cheia para equipes da Defesa Civil no Vale do Taquari e em Porto Alegre (Rio Grande do Sul).
Um modelo de fusão já calculou a probabilidade de cheia e o nível de risco a partir de réguas de rio e estações de chuva.
Esses números são finais: repita-os exatamente, sem recalcular, arredondar de outro jeito ou alterá-los.

Escreva:
- headline: o local, o nível de risco e a probabilidade.
- explanation: de 2 a 5 frases. Diga quais sinais mais moveram a estimativa e quanto, usando apenas os números de
  'efeito' e 'sem ele' e as leituras que estão na entrada. Mencione sinais que reduzem o risco, se forem relevantes.
  Se alguma régua estiver silenciosa, diga isso explicitamente, com o código da estação e há quanto tempo está sem
  leitura, e diga que a última leitura dela recebe menos peso (ou nenhum).
- drivers: os 1 a 4 sinais de maior efeito.
- silent_gauges: os códigos de todas as réguas silenciosas da entrada (lista vazia se não houver).

Regras: use apenas números, códigos de estação e nomes de lugares que aparecem na entrada. Não acrescente previsões,
alturas do rio, horários ou lugares que não estejam na entrada. Escreva em português do Brasil, com vírgula decimal
(por exemplo, 95,6%).
"""


@dataclass
class Deps:
    inp: AlertInput


def local_model():
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=os.environ.get("ALERT_BASE_URL", "http://localhost:8088/v1"),
        api_key=os.environ.get("ALERT_API_KEY", "local"),
    )
    return OpenAIChatModel(os.environ.get("ALERT_MODEL", "default_model"), provider=provider)


def model_settings() -> dict:
    return {
        "temperature": 0.0,
        "max_tokens": 800,
        "timeout": 900,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }


def build_agent(model=None, *, output_mode: Literal["tool", "prompted"] = "tool",
                audit_retry: bool = False, retries: int = 2, lang: Lang = DEFAULT_LANG) -> Agent[Deps, AlertDraft]:
    output = ToolOutput(AlertDraft, name="final_alert") if output_mode == "tool" else PromptedOutput(AlertDraft)
    agent = Agent(
        model if model is not None else local_model(),
        deps_type=Deps,
        output_type=output,
        instructions=INSTRUCTIONS_PT if lang == "pt" else INSTRUCTIONS,
        retries=retries,
        model_settings=model_settings(),
    )
    if audit_retry:
        @agent.output_validator
        def _audit(ctx: RunContext[Deps], draft: AlertDraft) -> AlertDraft:
            a = citation_audit(ctx.deps.inp, draft)
            if not a.ok:
                raise ModelRetry("The citation audit failed; fix the text (keep its language): " + audit_complaints(a))
            return draft

    return agent


def audit_complaints(a: Audit) -> str:
    parts = []
    if a.ungrounded_numbers:
        parts.append(f"these numbers are not in the input: {', '.join(a.ungrounded_numbers)}")
    if a.unknown_stations:
        parts.append(f"these station codes are not in the input: {', '.join(a.unknown_stations)}")
    if a.unknown_places:
        parts.append(f"these places are not in the input: {', '.join(a.unknown_places)}")
    if a.silent_not_mentioned:
        parts.append(f"say that these gauges are silent: {', '.join(a.silent_not_mentioned)}")
    if a.silent_field_mismatch:
        parts.append(f"silent_gauges must list exactly the silent gauges of the input (check: {', '.join(a.silent_field_mismatch)})")
    if a.wrong_level:
        parts.append(f"the risk level is not {', '.join(a.wrong_level)}")
    return "; ".join(parts)


def prompt(inp: AlertInput) -> str:
    if inp.lang == "pt":
        return f"Escreva o alerta para esta situação.\n\n{inp.text}"
    return f"Write the alert for this situation.\n\n{inp.text}"


def write_alert(state: FusedState | dict, agent: Agent[Deps, AlertDraft], lang: Lang = DEFAULT_LANG) -> tuple[Alert, dict]:
    inp = build_input(state, lang)
    t0 = time.monotonic()
    res = agent.run_sync(prompt(inp), deps=Deps(inp))
    draft = res.output
    audit = citation_audit(inp, draft)
    alert = Alert(place=inp.place, time_local=inp.time_local, probability=inp.probability, level=inp.level,
                  headline=draft.headline, explanation=draft.explanation, drivers=draft.drivers,
                  silent_gauges=draft.silent_gauges, audit=audit)
    usage = res.usage() if callable(res.usage) else res.usage
    meta = {"seconds": round(time.monotonic() - t0, 1), "requests": usage.requests,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
    return alert, meta


def summarize(path: Path) -> dict:
    """Audit pass rate and failure kinds per (output mode, audit retry) in an alerts JSONL file."""
    out: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        k = f"{r['output_mode']}{'+audit_retry' if r['audit_retry'] else ''}"
        d = out.setdefault(k, {"runs": 0, "errors": 0, "audit_ok": 0, "requests": 0, "seconds": 0.0, "failures": {}})
        d["runs"] += 1
        if "error" in r:
            d["errors"] += 1
            continue
        a = r["alert"]["audit"]
        d["audit_ok"] += a["ok"]
        d["requests"] += r["requests"]
        d["seconds"] += r["seconds"]
        for f in ("ungrounded_numbers", "unknown_stations", "unknown_places", "silent_not_mentioned",
                  "silent_field_mismatch", "wrong_level"):
            if a[f]:
                d["failures"][f] = d["failures"].get(f, 0) + 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--key-hours", type=Path, default=OUT_DIR / "key_hours.json")
    ap.add_argument("--out", type=Path, default=OUT_DIR / "alerts.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="0 = all key hours")
    ap.add_argument("--output-mode", choices=["tool", "prompted"], default="tool")
    ap.add_argument("--audit-retry", action="store_true", help="let the agent retry when the citation audit fails")
    ap.add_argument("--lang", choices=["pt", "en"], default=DEFAULT_LANG, help="language of the input block and the alert")
    ap.add_argument("--summary", action="store_true", help="only summarize --out, no model calls")
    args = ap.parse_args(argv)
    if args.summary:
        print(json.dumps(summarize(args.out), indent=1))
        return 0
    hours = json.loads(args.key_hours.read_text())
    if args.limit:
        hours = hours[: args.limit]
    agent = build_agent(output_mode=args.output_mode, audit_retry=args.audit_retry, lang=args.lang)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_ok = n_err = 0
    for kh in hours:
        rec = {"place": kh["place"], "kind": kh["kind"], "time_local": kh["state"]["t_local"],
               "output_mode": args.output_mode, "audit_retry": args.audit_retry, "lang": args.lang}
        try:
            alert, meta = write_alert(kh["state"], agent, args.lang)
            rec |= {"alert": alert.model_dump(), **meta}
            n_ok += alert.audit.ok
            print(f"{kh['place']:12} {kh['kind']:17} audit_ok={alert.audit.ok} {meta['seconds']} s  {alert.headline}", flush=True)
        except Exception as e:  # noqa: BLE001 - record and keep going
            n_err += 1
            rec["error"] = f"{type(e).__name__}: {e}"
            print(f"{kh['place']:12} {kh['kind']:17} ERROR {rec['error'][:200]}", flush=True)
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"done: {len(hours)} key hours, audit ok {n_ok}, errors {n_err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

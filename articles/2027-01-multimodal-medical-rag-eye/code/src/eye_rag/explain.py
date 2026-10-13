"""Explanation agent with a citation check, and the faithfulness scores.

    uv run --group vlm python -m eye_rag.explain run --arm retrieval --split test [--n 20]
    uv run --group vlm python -m eye_rag.explain run --arm shuffled --split test
    uv run python -m eye_rag.explain score

The agent explains each diagnosed label from the photo, from cited cases, or both;
`check_citations` verifies the answer without a model, and failures are retried, then
kept as unverified. The check proves the citations match the *text shown*, not that
the label is right: `score` measures both (docs/RESULTS.md, 2.4).

Research demo, not a medical device.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eye_rag.labels import NORMAL
from eye_rag.vlm import NORMAL_LABEL, Case, Label, VisionModel, _short_error, case_report, extract_json, label_menu

RUNS = Path("runs")


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Label
    source: Literal["image", "cases", "both"]
    cases: list[int] = Field(default_factory=list)
    reason: str = Field(default="", max_length=400)


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(min_length=1)


# --------------------------------------------------------------------------- the check


def _recorded(labels: Sequence[str]) -> set[str]:
    """A case's recorded findings in diagnosis vocabulary (NORMAL -> "normal")."""
    return {NORMAL_LABEL if x == NORMAL else x for x in labels}


def check_citations(e: Explanation, diagnosis: Sequence[str], case_labels: Sequence[Sequence[str]]) -> list[str]:
    """Problems with an explanation, as short sentences for the model (empty = verified)."""
    problems = []
    seen = Counter(f.label for f in e.findings)
    for lab in diagnosis:
        if seen[lab] == 0:
            problems.append(f"{lab} is in the diagnosis but has no explanation")
    for lab, n in seen.items():
        if lab not in diagnosis:
            problems.append(f"{lab} is explained but is not in the diagnosis")
        elif n > 1:
            problems.append(f"{lab} is explained {n} times; explain it once")
    k = len(case_labels)
    for f in e.findings:
        if f.source == "image" and f.cases:
            problems.append(f"{f.label}: source is \"image\" but it cites cases {f.cases}")
        if f.source != "image" and not f.cases:
            problems.append(f"{f.label}: source is \"{f.source}\" but it cites no case")
        for n in f.cases:
            if not 1 <= n <= k:
                problems.append(f"{f.label}: case {n} does not exist (cases are 1 to {k})")
            elif f.label not in _recorded(case_labels[n - 1]):
                problems.append(f"{f.label}: case {n} is cited for it, but case {n}'s recorded findings are {sorted(_recorded(case_labels[n - 1]))}")
    return problems


# --------------------------------------------------------------------------- the agent


INSTRUCTIONS = """You are assisting a research study on retinal fundus photographs (not clinical use).
You are shown {k} reference cases from a labelled archive, each with its recorded findings, and then a QUERY photograph.
The findings already given for the QUERY are: {diagnosis}.

Label codes:
{menu}

For EACH of those findings, and no others, say where it comes from:
- "image": you can see it in the QUERY photograph itself; cite no case.
- "cases": it comes from reference cases; cite the case numbers whose recorded findings include it.
- "both": you see it in the QUERY and reference cases with that recorded finding agree; cite them.
Only cite a case for a finding that appears in that case's recorded findings.
Answer with a single JSON object and nothing else, in this form:
{{"findings": [{{"label": "CODE", "source": "image" | "cases" | "both", "cases": [case numbers], "reason": "one sentence"}}, ...]}}"""


def build_parts(query: Path, cases: Sequence[Case], diagnosis: Sequence[str]) -> list[str | Path]:
    parts: list[str | Path] = [INSTRUCTIONS.format(k=len(cases), diagnosis=", ".join(diagnosis), menu=label_menu())]
    for i, c in enumerate(cases, 1):
        parts += [f"\nReference case {i}. Recorded findings: {case_report(c.labels)}", c.path]
    parts += ["\nQUERY photograph:", query, "\nJSON answer:"]
    return parts


@dataclass
class ExplainOutcome:
    explanation: Explanation | None
    attempts: int
    first_problems: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # of the last attempt; empty = verified
    raw: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def verified(self) -> bool:
        return self.explanation is not None and not self.problems


def explain(model: VisionModel, query: Path, cases: Sequence[Case], diagnosis: Sequence[str], retries: int = 2, max_tokens: int = 400) -> ExplainOutcome:
    """Ask for an explanation, check it, and retry with the list of problems."""
    parts = build_parts(query, cases, diagnosis)
    out = ExplainOutcome(None, 0)
    t = time.perf_counter()
    for attempt in range(retries + 1):
        out.attempts = attempt + 1
        if attempt == 0:
            p = parts
        else:
            listed = "\n".join(f"- {x}" for x in out.problems)
            p = [*parts[:-1], f"\nYour previous answer had these problems:\n{listed}\nFix them and reply with the JSON object only.\nJSON answer:"]
        text = model.generate(p, max_tokens)
        out.raw.append(text)
        try:
            e = Explanation.model_validate(json.loads(extract_json(text)))
            out.problems = check_citations(e, diagnosis, [c.labels for c in cases])
            out.explanation = e
        except (ValueError, ValidationError) as err:
            out.problems = [f"invalid answer: {_short_error(err)}"]
        if attempt == 0:
            out.first_problems = list(out.problems)
        if not out.problems:
            break
    out.seconds = time.perf_counter() - t
    return out


def run(model: VisionModel, arm: str, split: str, n: int | None, out_dir: Path = RUNS) -> Path:
    """Explain the diagnoses of one diagnose run (rows in runs/m2_vlm_{split}_{arm}.jsonl). Resumable."""
    from eye_rag.diagnose import subset
    from eye_rag.dedup import load_exclusions
    from eye_rag.rfmid import load_split

    src = {r["id"]: r for r in _rows(out_dir / f"m2_vlm_{split}_{arm}.jsonl")}
    recs = {r.id: r for r in load_split(split)}
    train = {r.id: r for r in load_split("train")}
    ids = [i for i in subset(list(recs), load_exclusions().get(split, frozenset()), None) if i in src and src[i]["labels"]]
    ids = ids if n is None else ids[:n]
    out = out_dir / f"m2_explain_{split}_{arm}.jsonl"
    done = {r["id"] for r in _rows(out)}
    todo = [i for i in ids if i not in done]
    print(f"explain {arm}/{split}: {len(ids)} diagnosed, {len(done)} done, {len(todo)} to run", file=sys.stderr)
    t0 = time.perf_counter()
    with out.open("a") as f:
        for j, qid in enumerate(todo, 1):
            r = src[qid]
            cases = [Case(train[c].path, tuple(labs)) for c, labs in zip(r["case_ids"], r["case_labels"])]
            o = explain(model, recs[qid].path, cases, r["labels"])
            f.write(json.dumps({
                "id": qid,
                "diagnosis": r["labels"],
                "findings": [x.model_dump() for x in o.explanation.findings] if o.explanation else None,
                "verified": o.verified,
                "attempts": o.attempts,
                "first_problems": o.first_problems,
                "problems": o.problems,
                "seconds": round(o.seconds, 2),
                "raw_last": o.raw[-1][:1500],
            }) + "\n")
            f.flush()
            if j % 10 == 0 or j == len(todo):
                el = time.perf_counter() - t0
                print(f"  {j}/{len(todo)}  {el / j:.1f}s/img  eta {el / j * (len(todo) - j) / 60:.0f} min", file=sys.stderr)
    (out_dir / f"m2_explain_{split}_{arm}.meta.json").write_text(json.dumps({"model": model.name, "arm": arm, "split": split, "n_requested": n, "n_in_subset": len(ids), "retries": 2}, indent=1))
    return out


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


# --------------------------------------------------------------------------- scores


def _conditions(labels: Sequence[str] | None) -> set[str]:
    return {x for x in labels or [] if x not in (NORMAL_LABEL, NORMAL)}


def diagnosis_citations(rows: Sequence[dict]) -> dict:
    """The free check on the diagnosis step's own `cited_cases` (no extra model call)."""
    ok = [r for r in rows if r["labels"]]
    cites = [r for r in ok if r["cited_cases"]]
    out_of_range = [r for r in cites if any(not 1 <= n <= len(r["case_labels"]) for n in r["cited_cases"])]
    supported = [r for r in cites if r not in out_of_range and all(set(r["labels"]) & _recorded(r["case_labels"][n - 1]) for n in r["cited_cases"])]
    return {
        "n": len(ok),
        "cites_any_case": round(len(cites) / len(ok), 4) if ok else None,
        "cites_out_of_range": len(out_of_range),
        "every_cited_case_shares_a_label": round(len(supported) / len(cites), 4) if cites else None,
    }


def faithfulness(rows_true: Sequence[dict], rows_shuf: Sequence[dict], rows_zero: Sequence[dict], truth: dict[str, set[str]]) -> dict:
    """Does the answer follow the case labels shown? Compares the retrieval arm (true case
    labels) with the shuffled arm (same images, wrong labels) on the same queries."""
    t = {r["id"]: r for r in rows_true if r["labels"]}
    z = {r["id"]: r for r in rows_zero if r["labels"]}
    pairs = [(t[r["id"]], r) for r in rows_shuf if r["labels"] and r["id"] in t]
    if not pairs:
        return {"n": 0}

    def shown(r):
        return set().union(*map(_recorded, r["case_labels"])) - {NORMAL_LABEL}

    def share(rows, sets):
        num = sum(len(_conditions(r["labels"]) & s) for r, s in zip(rows, sets))
        den = sum(len(_conditions(r["labels"])) for r in rows)
        return round(num / den, 4) if den else None

    a, b = [p[0] for p in pairs], [p[1] for p in pairs]
    hidden = [set().union(*map(_recorded, r["true_case_labels"])) - {NORMAL_LABEL} for r in b]
    # labels in the shuffled answer that only the wrong text can explain: shown, not in any
    # true case, not in the zero-shot answer, and not true for the query
    injected = [(_conditions(r["labels"]) & shown(r)) - h - _conditions(z.get(r["id"], {}).get("labels")) - truth[r["id"]] for r, h in zip(b, hidden)]
    return {
        "n": len(pairs),
        "answer_changed": round(float(np.mean([set(x["labels"]) != set(y["labels"]) for x, y in pairs])), 4),
        "labels_in_shown_cases": {"true_labels_shown": share(a, [shown(r) for r in a]), "shuffled_labels_shown": share(b, [shown(r) for r in b])},
        "shuffled_answer_labels_in_hidden_true_cases": share(b, hidden),
        "images_with_an_injected_wrong_label": round(float(np.mean([bool(x) for x in injected])), 4),
        "injected_wrong_labels": sum(len(x) for x in injected),
        "normal_answers": {"true_labels_shown": round(float(np.mean([r["labels"] == [NORMAL_LABEL] for r in a])), 4), "shuffled_labels_shown": round(float(np.mean([r["labels"] == [NORMAL_LABEL] for r in b])), 4)},
    }


def explanation_scores(rows: Sequence[dict], truth: dict[str, set[str]]) -> dict:
    """Verification rates, problem types, sources, and whether verified citations were right."""
    if not rows:
        return {"n": 0}
    kinds = Counter()
    for r in rows:
        for p in r["first_problems"]:
            kinds[_kind(p)] += 1
    findings = [(r["id"], f) for r in rows if r["verified"] for f in r["findings"]]
    cited = [(i, f) for i, f in findings if f["source"] != "image"]
    right = [(i, f) for i, f in cited if f["label"] in (truth[i] or {NORMAL_LABEL})]
    return {
        "n": len(rows),
        "verified_first_try": round(float(np.mean([not r["first_problems"] for r in rows])), 4),
        "verified_after_retries": round(float(np.mean([r["verified"] for r in rows])), 4),
        "unverified": sum(not r["verified"] for r in rows),
        "first_try_problem_kinds": dict(kinds.most_common()),
        "sources_in_verified": dict(Counter(f["source"] for _, f in findings)),
        "verified_case_citations": len(cited),
        "verified_case_citations_label_true": round(len(right) / len(cited), 4) if cited else None,
        "mean_seconds": round(float(np.mean([r["seconds"] for r in rows])), 2),
    }


def _kind(problem: str) -> str:
    for key, name in (("no explanation", "label not explained"), ("is not in the diagnosis", "explains an undiagnosed label"), ("explained", "explained twice"),
                      ("does not exist", "case does not exist"), ("recorded findings are", "cited case lacks the label"), ("cites no case", "source says cases, none cited"),
                      ("but it cites cases", "source says image, cases cited"), ("invalid answer", "invalid JSON / schema")):
        if key in problem:
            return name
    return "other"


def score(out_dir: Path = RUNS, split: str = "test") -> dict:
    from eye_rag.m2 import COLUMNS, _metrics, vlm_matrix
    from eye_rag.rfmid import load_split

    recs = load_split(split)
    truth = {r.id: set(r.labels) for r in recs}
    rows = {a: _rows(out_dir / f"m2_vlm_{split}_{a}.jsonl") for a in ("zero_shot", "retrieval", "shuffled")}
    result: dict = {"split": split, "diagnosis_citations": diagnosis_citations(rows["retrieval"])}
    result["faithfulness"] = faithfulness(rows["retrieval"], rows["shuffled"], rows["zero_shot"], truth)
    # macro-F1 of the three VLM arms on the images all three have
    common = set.intersection(*(set(r["id"] for r in v) for v in rows.values())) if all(rows.values()) else set()
    if common:
        from eye_rag.evaluate import compute

        c = compute()
        pos = {r.id: i for i, r in enumerate(recs)}
        ids = sorted(common, key=lambda x: int(x.split("/")[1]))
        yt = c["y"][split][[pos[i] for i in ids]]
        present = [j for j in range(1, len(COLUMNS)) if yt[:, j].sum() > 0]
        result["macro_f1_same_images"] = {a: _metrics(yt, vlm_matrix([{r["id"]: r for r in v}[i] for i in ids])[1], c["frequent"], present) for a, v in rows.items()}
    result["explanations"] = {a: explanation_scores(_rows(out_dir / f"m2_explain_{split}_{a}.jsonl"), truth) for a in ("retrieval", "shuffled")}
    (out_dir / f"m2_explain_{split}.json").write_text(json.dumps(result, indent=1))
    return result


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["run", "score"])
    p.add_argument("--arm", choices=["retrieval", "shuffled"], default="retrieval")
    p.add_argument("--split", default="test", choices=["val", "test"])
    p.add_argument("--n", type=int, default=None)
    p.add_argument("--out", type=Path, default=RUNS)
    a = p.parse_args(argv)
    if a.command == "run":
        from eye_rag.vlm import MlxVlm

        run(MlxVlm(), a.arm, a.split, a.n, a.out)
    else:
        print(json.dumps(score(a.out, a.split), indent=1))
    print("done", file=sys.stderr)


if __name__ == "__main__":
    main()

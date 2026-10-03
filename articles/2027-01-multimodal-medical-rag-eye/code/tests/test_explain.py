from pathlib import Path

from eye_rag.diagnose import shuffled_case_labels
from eye_rag.explain import Explanation, check_citations, diagnosis_citations, explain, explanation_scores, faithfulness
from eye_rag.vlm import Case


def ex(*findings):
    return Explanation.model_validate({"findings": [dict(zip(("label", "source", "cases"), f)) for f in findings]})


CASES = [("DR", "MH"), ("NORMAL",), ("ODC",)]


def test_check_passes_a_consistent_explanation():
    assert check_citations(ex(("DR", "both", [1]), ("ODC", "image", [])), ["DR", "ODC"], CASES) == []
    assert check_citations(ex(("normal", "cases", [2])), ["normal"], CASES) == []


def test_check_finds_each_kind_of_problem():
    p = check_citations(ex(("DR", "cases", [3]), ("MH", "image", [1]), ("ODC", "cases", []), ("ARMD", "both", [4])), ["DR", "MH", "ODC", "TSLN"], CASES)
    text = "\n".join(p)
    assert "TSLN is in the diagnosis but has no explanation" in text
    assert "ARMD is explained but is not in the diagnosis" in text
    assert "DR: case 3 is cited for it, but case 3's recorded findings are ['ODC']" in text
    assert 'MH: source is "image" but it cites cases [1]' in text
    assert 'ODC: source is "cases" but it cites no case' in text
    assert "ARMD: case 4 does not exist" in text
    assert "explained 2 times" in "\n".join(check_citations(ex(("DR", "image", []), ("DR", "image", [])), ["DR"], CASES))


class Stub:
    name = "stub"

    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def generate(self, parts, max_tokens):
        self.prompts.append(parts)
        return self.answers.pop(0)


def test_explain_feeds_problems_back_and_verifies():
    m = Stub(['{"findings": [{"label": "DR", "source": "cases", "cases": [3]}]}', '{"findings": [{"label": "DR", "source": "cases", "cases": [1]}]}'])
    cases = [Case(Path(f"{i}.jpg"), labs) for i, labs in enumerate(CASES)]
    o = explain(m, Path("q.jpg"), cases, ["DR"])
    assert o.verified and o.attempts == 2 and "case 3" in o.first_problems[0]
    assert "case 3's recorded findings" in m.prompts[1][-1]
    assert "The findings already given for the QUERY are: DR." in m.prompts[0][0]


def test_explain_keeps_an_unverified_answer_after_retries():
    o = explain(Stub(["no json"] * 3), Path("q.jpg"), [], ["DR"], retries=2)
    assert not o.verified and o.attempts == 3 and o.problems[0].startswith("invalid answer")


def test_shuffled_labels_are_seeded_and_never_a_true_case_label():
    true = [("DR",), ("DR", "MH"), ("NORMAL",)]
    pool = [("DR",), ("NORMAL",), ("ODC",), ("ARMD",), ("DR", "MH")]
    a = shuffled_case_labels("test/1", true, pool)
    assert a == shuffled_case_labels("test/1", true, pool) and len(a) == 3
    assert all(x not in true for x in a)


def row(i, labels, case_labels, cited=(), true_case_labels=None):
    r = {"id": f"test/{i}", "labels": labels, "case_labels": case_labels, "cited_cases": list(cited)}
    if true_case_labels:
        r["true_case_labels"] = true_case_labels
    return r


def test_diagnosis_citations():
    rows = [row(1, ["DR"], [["DR"], ["MH"]], [1]), row(2, ["DR"], [["DR"], ["MH"]], [2]), row(3, ["DR"], [["DR"]], [5]), row(4, ["ODC"], [["DR"]]), row(5, None, [])]
    d = diagnosis_citations(rows)
    assert d["n"] == 4 and d["cites_any_case"] == 0.75 and d["cites_out_of_range"] == 1
    assert d["every_cited_case_shares_a_label"] == 0.3333


def test_faithfulness_counts_labels_that_follow_the_wrong_text():
    true = [row(1, ["DR"], [["DR"], ["DR"]]), row(2, ["normal"], [["NORMAL"]])]
    shuf = [row(1, ["ARMD"], [["ARMD"], ["ODC"]], true_case_labels=[["DR"], ["DR"]]), row(2, ["normal"], [["MH"]], true_case_labels=[["NORMAL"]])]
    zero = [row(1, ["MH"], []), row(2, ["normal"], [])]
    f = faithfulness(true, shuf, zero, {"test/1": {"DR"}, "test/2": set()})
    assert f["n"] == 2 and f["answer_changed"] == 0.5
    assert f["labels_in_shown_cases"] == {"true_labels_shown": 1.0, "shuffled_labels_shown": 1.0}
    assert f["shuffled_answer_labels_in_hidden_true_cases"] == 0.0
    assert f["images_with_an_injected_wrong_label"] == 0.5 and f["injected_wrong_labels"] == 1


def test_explanation_scores_separate_verified_from_right():
    rows = [
        {"id": "test/1", "verified": True, "first_problems": [], "seconds": 1, "findings": [{"label": "DR", "source": "cases", "cases": [1]}, {"label": "MH", "source": "image", "cases": []}]},
        {"id": "test/2", "verified": True, "first_problems": ["DR: case 9 does not exist (cases are 1 to 3)"], "seconds": 3, "findings": [{"label": "ARMD", "source": "both", "cases": [1]}]},
        {"id": "test/3", "verified": False, "first_problems": ["invalid answer: x"], "seconds": 2, "findings": None},
    ]
    s = explanation_scores(rows, {"test/1": {"DR"}, "test/2": {"DR"}, "test/3": set()})
    assert s["verified_first_try"] == 0.3333 and s["verified_after_retries"] == 0.6667 and s["unverified"] == 1
    assert s["first_try_problem_kinds"] == {"case does not exist": 1, "invalid JSON / schema": 1}
    assert s["verified_case_citations"] == 2 and s["verified_case_citations_label_true"] == 0.5

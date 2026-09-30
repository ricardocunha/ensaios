from compliance_agents.limits import GuaranteeFacts, TermFacts, decide_guarantee, decide_term


def g(percent, justified=False, required=True):
    return GuaranteeFacts(guarantee_required=required, percent=percent, justification_quote="complexidade" if justified else "",
                          section_id=1, evidence="", confidence=1)


def t(months, total=None, continuous=True):
    return TermFacts(continuous=continuous, initial_months=months, max_total_months=total, section_id=1, evidence="", confidence=1)


def test_guarantee_limits_art_98():
    assert decide_guarantee(g(None, required=False))[0] == "not_applicable"
    assert decide_guarantee(g(5))[0] == "compliant"
    assert decide_guarantee(g(8))[0] == "violation"
    assert decide_guarantee(g(8, justified=True))[0] == "compliant"
    assert decide_guarantee(g(12, justified=True))[0] == "violation"


def test_term_limits_arts_106_107():
    assert decide_term(t(12, 120))[0] == "compliant"
    assert decide_term(t(60))[0] == "compliant"
    assert decide_term(t(72))[0] == "violation"
    assert decide_term(t(12, 144))[0] == "violation"
    assert decide_term(t(6, continuous=False))[0] == "not_applicable"

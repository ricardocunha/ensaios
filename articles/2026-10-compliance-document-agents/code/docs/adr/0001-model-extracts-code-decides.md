# Limit rules: the model extracts values, code applies the law

For rules that compare a value with a legal limit (guarantee ≤ 5%, or ≤ 10% with justification, art. 98; continuous-service term ≤ 5 years and ≤ 10 with extensions, arts. 106–107), the reviewer no longer gives a verdict. It extracts typed facts (`GuaranteeFacts`, `TermFacts`: percentage, justification quote, months, whether the object is continuous) and `limits.py` decides.

The baseline reviewer quoted "12 (doze) meses" correctly and then said it exceeded "5 anos". On these two rules it raised 23 false alarms in 40 findings. With extraction plus code, the v2 run has 2 (both on the term rule), and all 11 hard compliant cases (8% *with* justification, a 60-month term, "Comarca de <seat>") are right.

## Considered options

- **Better instructions** ("convert to months before comparing"): rejected; the same instruction-only approach had already failed on the *foro* rule, and the arithmetic is trivial in code.
- **Thinking mode** on Qwen3-8B: minutes per call on a laptop, and it still misjudged the *foro* case.
- **Code-only extraction** (regex on percentages and months): brittle on real contracts, and "is the object continuous?" needs reading the object clause.

## Consequences

The extractor still has to read the right clause: it first decided "continuous" from the term clause and missed a planted 72-month term, so `HINTS` in `limits.py` say where each fact lives. Same split as the CNH article's ADR 0003: the model reads, rules decide.

# The Teacher is an open-weight model whose license allows training on its outputs

The Teacher's outputs become the Student's training data. smithtune's data-rights terms (accepted before use) forbid using it to circumvent model licenses that restrict "distillation, training competing models, or other uses of model outputs", and Anthropic's terms restrict using Claude's outputs to train AI models. So the Teacher is **DeepSeek-V4-Pro-0813 (MIT license)** on Baseten Model APIs, not Claude Sonnet 5. It is set with `TEACHER_MODEL`, and its runs trace to a separate LangSmith project (`cnh-teacher-deepseek`).

The Claude runs made while debugging the Extractor (three 20-run checks and one 300-run main run, in project `cnh`) are kept for the record but never enter a smithtune dataset or any training data.

## Considered Options

- **Claude Sonnet 5 as the Teacher** (the original plan): the strongest tool user we tried and cheapest with prompt caching. Rejected for license reasons.
- **gpt-oss-120b (Apache-2.0):** permissive and about 10× cheaper per token, but a weaker agent. It's the fallback.
- **GLM-5.3 / Kimi-K3:** custom licenses whose text we couldn't verify.

## Consequences

Through Baseten's OpenAI-compatible endpoint, DeepSeek's list-valued tool arguments arrived concatenated, so the submit tool takes filiação as one `"PAI / MÃE"` string. Quality and cost ended up on par with Claude: 266/300 exact, about $0.016 per run.

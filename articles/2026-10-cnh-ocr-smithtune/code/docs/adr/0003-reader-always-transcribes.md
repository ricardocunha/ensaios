# The Reader always transcribes; "is this a CNH?" is decided from text

In rounds 1 and 2 the Reader was also the gate: it answered `NÃO É CNH` for anything that wasn't a CNH. Fine-tuned on synthetic cards, it learned "CNH = my renderer's look". On real CNH templates (BID) it wrongly rejected 48/70 cards in round 1 and 30/70 after domain randomization in round 2. Yet it read the cards it accepted almost perfectly. So from round 3 the Reader transcribes every document, decoys included, as `LABEL: value` lines. The CNH/Non-CNH decision moves to the text side: the Extractor's `reject_document` in the full pipeline, and a deterministic label rule (`cnh_ocr/gate.py`: at least two CNH-only labels such as CAT. HAB., Nº REGISTRO, 1ª HABILITAÇÃO) as the Stage 1 stand-in and pre-filter.

This matches the glossary, where a Rejection was always the Extractor's outcome. It also means the vision model never has to learn what a CNH "looks like", only how to read one.

## Consequences

- The Reader prompt changes (`READER_PROMPT_V3`, no refusal instruction), and decoy training targets become transcriptions of what the decoy prints. v1/v2 adapters keep the old prompt (`--prompt v1`).
- A document that prints CNH-only labels but isn't a CNH would pass the rule gate. The Extractor, which validates checksums and dates, is the backstop.

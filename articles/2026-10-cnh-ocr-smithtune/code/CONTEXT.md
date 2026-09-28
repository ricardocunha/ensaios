# CNH Extraction

Reads a photo or screenshot of a Brazilian driver's license (CNH) and turns it into validated structured data. It also serves as a real-world test of LangSmith's smithtune.

## Language

### Documents

**CNH**:
Carteira Nacional de Habilitação, the Brazilian driver's license. In scope are the physical 2022+ model and the CNH Digital.
_Avoid_: driver license, ID, document (when you mean specifically a CNH)

**CNH Digital**:
The app/PDF rendition of a CNH, captured as a screenshot or PDF render.
_Avoid_: e-CNH, digital license

**Non-CNH**:
Any input image that is not a CNH (RG, CPF card, invoice, random photo). The system rejects it rather than extracting from it.
_Avoid_: invalid document, other document

**Synthetic CNH**:
A generated CNH image with fake data and a visible "AMOSTRA / SYNTHETIC" mark, with its ground truth known by construction. It is the only kind of CNH used for training.
_Avoid_: fake CNH, mock

**Private Real Sample**:
One of a handful of real CNHs, used only for a local sanity check. It is never committed, published or shown.

### Pipeline

**Extraction**:
Producing the validated CNH Record from a CNH image. It is the system's only job; classifying document types is out of scope.
_Avoid_: identification, parsing, recognition

**Stage 1 (Reader)**:
The vision OCR model that turns a document image into a Transcription. It reads; it never decides whether the document is a CNH (ADR-0003).
_Avoid_: OCR step, vision model

**Stage 2 (Extractor)**:
The text-only, tool-using agent that turns a Transcription into a CNH Record. It fixes OCR errors and runs checksum validation.
_Avoid_: post-processor, parser, LLM step

**Transcription**:
What the Reader outputs: one `LABEL: value` line per printed field, values exactly as they appear on the document, with OCR errors left in. Unlabeled text goes on its own lines. It is never validated or normalized.
_Avoid_: OCR output, raw text

**CNH Gate**:
The text-side check that a Transcription is a CNH: it must carry at least two CNH-only labels (CAT. HAB., Nº REGISTRO, 1ª HABILITAÇÃO, VALIDADE, PERMISSÃO, ACC). It is a cheap pre-filter before the Extractor, not a replacement for the Extractor's judgment.
_Avoid_: classifier, filter

**CNH Record**:
The final structured, validated output for one CNH. A field whose line is absent or illegible in the Transcription is null. It is never guessed, and its absence never turns the CNH into a Rejection.
_Avoid_: result, JSON, extraction output

**Rejection**:
The outcome for a Non-CNH, decided from the Transcription (CNH Gate, then the Extractor), never by the Reader. An incomplete or partly illegible CNH is not a Rejection; it is a CNH Record with null fields.

### Training

**Teacher**:
The frontier model that runs the Extractor to produce Trajectories.
_Avoid_: oracle, labeler

**Student**:
The smaller open model fine-tuned with smithtune to imitate the Teacher's Extractor behavior.
_Avoid_: tuned model, small model

**Trajectory**:
One recorded Extractor run in LangSmith: the messages and tool calls from Transcription to CNH Record or Rejection.
_Avoid_: trace (when you mean a full run), log

**Golden Trajectory**:
A Trajectory whose final CNH Record matches the ground truth and that passed triage. Only Golden Trajectories are used to train the Student.
_Avoid_: good trace, clean example

**Base OCR Model**:
One of the three vision models evaluated for the Reader role (Chandra 2, PaddleOCR-VL-1.6, Qwen3.5-9B).

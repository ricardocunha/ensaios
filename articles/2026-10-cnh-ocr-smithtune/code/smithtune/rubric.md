# Selection criteria: CNH Extractor trajectories

Keep a trajectory (score 1) only if **all** of these hold:

1. **Correct outcome type.** If the transcription is a CNH, the agent ends with exactly one `submit_cnh_record` call. If it is not a CNH (RG, invoice, unrelated text), it ends with `reject_document` and never submits.
2. **Checksums verified before submitting.** The agent called `validate_cpf` and `validate_cnh_number` before `submit_cnh_record`. When a check failed, it called `suggest_ocr_fixes` and used a correction only if exactly one candidate was returned.
3. **No invented data.** Every submitted value can be traced to the transcription, possibly after an evident OCR fix (O→0, S→5, A8→AB, date separators). Optional fields that are absent from the transcription are null, not guessed.
4. **Dates normalized.** Submitted dates are DD/MM/AAAA, and `check_dates` was called. If it reported problems, the agent re-read the transcription before submitting.
5. **Efficient.** No repeated identical tool calls and no more than one `submit_cnh_record` call.

Drop it (score 0) if the agent hallucinates a field, submits a CPF or CNH number whose checksum failed without trying `suggest_ocr_fixes`, or submits for a non-CNH.

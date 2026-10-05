# Faithfulness is tested by shuffling the retrieved cases' labels; the citation check is reported separately from correctness

"The model cites the cases it used" can't be checked by reading its explanations: an explanation is generated text. So faithfulness is tested by intervention: the retrieval arm is re-run with the **same retrieved case images** and **wrong labels** (each case gets a random other training case's label set, never one of the query's true case label sets; seeded per query). If the answer follows the images, the score should hold; if it follows the text, it should fall towards zero-shot.

The explanation agent's citations are checked in code (labels covered once, cases exist, source agrees with citations, each cited case records the label it's cited for), with feedback and up to 2 retries. The check is run on both arms, and **verified** is reported next to **verified and true for the image**, never instead of it.

## Considered options

- **Permuting labels among the 3 retrieved cases**: rejected; neighbours often share labels, so a permutation frequently changes nothing.
- **Blank images with true labels** (the reverse test): not run; it would show whether the text alone reproduces the gain, but a blank image is out of distribution for the model. Possible follow-up.
- **Tuning the explanation prompt until the check passes**: rejected; the prompt was set on a 20-image validation pilot and left alone.
- **An LLM judge of explanation quality**: rejected; it would grade the same kind of text that is under test.

## Consequences

Result (docs/RESULTS.md §2.4, §3): shuffling erased the retrieval gain (0.298 → 0.056; zero-shot 0.058), and the check verified 90.0 % (true) vs 89.3 % (shuffled) of explanations, with 48.8 % vs 12.2 % of verified case citations true for the image. Costs one extra VLM run and one extra explanation run per evaluation (~1.3 h and ~2 h on an M4 Pro for 609 images).

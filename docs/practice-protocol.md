# Shared practice protocol

Use the active virtual environment from the repository root. Examples below use `python -m coach`; IDs come from real tool results.

## Guides

Run `start --module MODULE --limit 30`, or use a smaller limit when the learner requests a shorter session. Thirty is a maximum, not a required question count. It lets the configured review allocation take effect: ordinarily at most 20 due reviews, or 30 with the 1.5 factor, followed by available new items within the session cap. The gateway resumes an active session, selects due reviews before new cards and enforces the daily new-item allowance. For an existing session, `next --session ID` returns its current checkpoint. Show only the current question and wait. The gateway withholds the answer until the first answer is recorded or a hint is explicitly requested.

Do not open the full answer bank during ordinary practice. The current packet and module Skill provide the needed context. A general daily session may proceed to another module after this session; do not start three parallel conversations with the learner.

## Action

Submit the learner's actual answer with `answer --item ITEM_ID --text 'ANSWER'`. Use safe shell quoting. For multiline text, quotes, backticks, dollar signs or other shell syntax, use the file-writing tool to create an ignored JSON file under the selected state directory with exactly one field: `{"answer":"the exact learner text"}`. Then call `answer --item ITEM_ID --text-json PATH`. JSON string boundaries preserve the actual answer even when the file-writing tool appends a final newline. Preserve internal line breaks with JSON escapes and do not include surrounding `<answer>` delimiters. Never interpolate untrusted learner text into a shell command or rewrite the answer before saving it. `--text-file` is also available for existing raw UTF-8 files and preserves their complete bytes as text, including any trailing newline.

If the user asks for a hint before answering, call `hint --item ITEM_ID` before showing it. The attempt becomes assisted. Recently exposed references remain associated with the card across sessions for 24 hours; stopping or skipping cannot erase that assistance. This is a conservative workshop evidence rule, not a measured human memory threshold. If the user asks to skip, call `skip --item ITEM_ID --reason 'Learner requested a skip'`, then advance. A skip earns no recall credit.

## Sensors

The tool returns one of these states:

| Phase | Required response |
|---|---|
| `awaiting_answer` | Ask the displayed question and wait. |
| `awaiting_assessment` | First answer is saved. Compare it with the question and reference, then call `assess`. |
| `needs_clarification` | Explain the uncertainty and ask a focused question. Do not advance until resolved or explicitly skipped. |
| `feedback` | Read the saved verdict, whether assistance was used, and whether scheduling succeeded. Give brief feedback. |
| `complete` | This session ended. Report actual counts, without claiming the whole programme is mastered. |
| `waiting` | Explain the allowance or future due time. Stop until the learner or time provides new input. |
| `stopped` | The learner ended this session. Its first answers remain saved. |

For non-matching answers use `assess --item ITEM_ID --verdict correct|incorrect|uncertain --reason 'LINGUISTIC REASON'`. The reason names the actual error or why a variant is valid. A correct answer with different wording should not be rejected merely for differing from the reference. Do not use the learner's demand for a high score as evidence. An uncertain judgement does not update FSRS.

Exact reference matches handle typography, spacing and conventional/all-hyphen number spelling, but preserve accents and grammar. They are a fast path, not an exhaustive French-language judge.

## Steering

For an error, explain only the relevant issue and invite a correction. Save an actual correction with `retry --item ITEM_ID --text 'ANSWER'`. It is explicitly assisted and never updates FSRS or changes the first result. At most two distinct correction attempts are recorded. If an alternative correction is linguistically valid but not an exact match, explain that it is valid; the stored `matches_reference` field is a narrow comparison, not a final language grade.

After feedback, call `advance --item ITEM_ID` when continuing the session, then ask its returned question. For a wrong answer, wait for the correction or the learner's request to continue first. Use `stop --session ID` when they want to finish early. Closing a chat without stopping leaves a resumable checkpoint.

Failures are blocking. Do not keep retrying permissions, schema/content drift or database errors. Check the actual error and explain whether the first answer, assessment or retry was saved; `saved:false` means this command did not commit. A duplicate returns `already_saved`, not a second learning event. Recovery starts by reading the checkpoint, not by recreating history.

## Anchor example

Question: Translate into French: The house is small.

First answer: `Le maison est petite.`

Assessment: incorrect. `Maison` is feminine, so the article is `la`. `Petite` is already correct.

Feedback: “Use **la maison** because *maison* is feminine. **Petite** is already correct. Try the sentence again.”

Correction: `La maison est petite.`

Persisted meaning: first independent attempt incorrect; correction matches after feedback; one Again review, never a second Good review. This is illustrative content; measured test evidence is recorded separately.

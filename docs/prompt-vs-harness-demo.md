# Demonstrate what the harness adds to a prompt and knowledge base

Both approaches can explain the French correctly. In this demonstration, the harness recovers the learning record in a fresh conversation and protects that record from invalid updates. Prompt plus a static knowledge base needs someone to supply the missing history.

This is a five-minute workshop walkthrough of **seven actual Codex calls**, recorded on 22 October 2026 with a synthetic learner. The [reviewed evidence](../validation/prompt-kb-demo.json) contains the actual responses, source hashes, configuration and 41 passing execution/state checks. It is a small capability demonstration, not a statistical performance benchmark.

## Establish a fair comparison

Both arms receive the same relevant French cards and coaching rules. The prompt-only coach is explicitly told to preserve the first answer, distinguish an assisted correction, accept valid French and admit missing history. It has a strong prompt, not an intentionally weak one.

| Prompt + static knowledge base | French Recall Coach harness |
|---|---|
| Same teaching content and evidence rules in the prompt | Same teaching content and evidence rules, plus repository instructions and Skills |
| No tools, writes or durable learner record | Executable gateway, validated state and scheduling |
| Conversation history supplied during the initial exchange | Same initial history, plus actual saved evidence |
| Fresh conversation receives no earlier transcript | Fresh conversation receives no earlier transcript, but can retrieve its state |

The baseline made zero observed tool calls. Both arms used the same Codex CLI default and common settings; the exact backend model revision was not pinned. Each request used a fresh process. For the first exchange, the runner supplied each arm's exact earlier transcript to represent continuing conversation context. It removed that transcript for the restart test.

The earlier no-Skill baseline in this repository retained the engine. That was a different comparison and could not establish the value of the full harness over prompt + KB alone.

## 1. Show that both can teach the language

The question is:

> Translate into French: The house is small.

The learner answers:

> Le maison est petite.

Both actual responses identify **Le → La**, because *maison* is feminine. Both recognise that **petite was already correct**. There is no demonstrated teaching-quality advantage here.

Now provide:

> La maison est petite.
> Please record my correction and continue to the next question.

Both accept the correction, retain the distinction from the first error and ask for the French expression for **apartment / flat, including the definite article**.

Inspect what happened behind the responses:

| Evidence | Prompt + KB | Harness |
|---|---|---|
| First answer was incorrect | Expressed in the conversation | Stored as the immutable first attempt |
| Corrected answer was assisted | Expressed in the conversation | Stored separately as an assisted retry |
| Again rating | Decision expressed in chat | One actual FSRS scheduling update |
| Next item | Stated in the conversation | Saved checkpoint at `v002` |

The word “saved” is not the test. The persisted rows and scheduling record are.

## 2. Open a fresh conversation

Give both the same request without the earlier transcript:

> Resume my vocabulary practice. What happened on my last item, and where should I continue?

The prompt + KB response begins:

> I don’t have a previous learner record, so I can’t tell what happened on your last item or where you left off.

That is an honest limitation. It then asks the learner to supply the exchange.

The harness retrieves the original **Le maison est petite.**, its incorrect judgement, the assisted **La maison est petite.** correction and the single scheduling update. It reports that one of three items is complete, then resumes the apartment question. The records and checkpoint remain unchanged during this read.

The practical gain is that the learner can continue without reconstructing the previous conversation.

## 3. Give the simpler setup its missing history

Paste its exact earlier exchange into the prompt + KB arm and repeat the resume request.

It now explains the original error, recognises the assisted correction and asks the correct next question. Keep this result visible: the simpler approach can reason over the history when someone provides it.

This comparison identifies the useful component: the harness maintains and retrieves the changing learner record. If a chat product already retains and retrieves that history, include that capability in a separate comparison. If a knowledge base is automatically updated after each attempt, it is already serving as part of a state-management system.

## 4. Show a check that does not depend on the model's wording

The runner also submits two deliberate operations directly to the actual gateway:

| Operation | Observed result |
|---|---|
| Replace the original first answer with the corrected sentence | Rejected with `immutable_answer` |
| Submit the identical original answer again | Returned `already_saved`; no duplicate attempt or scheduling update |

This is an intentional tool-boundary probe. It is not a claim that the prompt-only model made either mistake. It demonstrates that the gateway can protect the record even when a caller requests an invalid update.

## Run it again

After completing the repository setup, run:

```sh
.venv/bin/python scripts/demo_prompt_kb_comparison.py
```

This launches seven real Codex calls, at most two concurrently, and uses the signed-in account's allowance. It requires macOS/Linux, the repository virtual environment and an installed Codex CLI. Raw transcripts and disposable synthetic state stay under ignored `.test-runs/`. The command prints the new report path; review the responses as well as the automatic checks.

To check only workspace preparation without calling a model:

```sh
.venv/bin/python scripts/demo_prompt_kb_comparison.py --prepare-only
```

The observed gain is automatic continuity and executable protection of learning evidence. This run does not establish better French knowledge, faster replies, lower cost or improved long-term learning.

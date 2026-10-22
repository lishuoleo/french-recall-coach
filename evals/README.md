# Real Codex evaluation

These cases exercise the actual project instructions, Skills and local gateway through fresh Codex CLI processes. They complement deterministic unit tests. They do not replace them or prove that a learner has mastered French.

All inputs and learner profiles are synthetic. Fixtures use the real `Coach` methods to initialise sessions, save first answers, assess them and advance checkpoints. Only `persistence_failure` deliberately corrupts a disposable database after creating it normally, to test honest failure handling and preservation.

## Run

Use the repository virtual environment and an installed, signed-in Codex CLI. The runner makes no model override and uses the CLI default with user configuration omitted. It invokes `codex exec --ephemeral --ignore-user-config --sandbox workspace-write --json` against each isolated workspace.

```sh
.venv/bin/python scripts/run_codex_evals.py --list
.venv/bin/python scripts/run_codex_evals.py --cases start_vocab,wrong_article --jobs 1
.venv/bin/python scripts/run_codex_evals.py --jobs 2
.venv/bin/python scripts/run_codex_evals.py --baseline --jobs 2
```

Choose exactly the same `--cases` in both arms for a subset comparison. Each process has a 600-second limit, and the runner terminates its process group on timeout. At most two Codex processes run concurrently. The runner exits non-zero when an automated check or process fails; manual review remains required even when it exits zero.

Each run freezes a copy of the engine, curriculum, instructions and documentation under `.test-runs/`. Every case gets its own Git workspace, state and fresh Codex process. The repository `.venv` is linked into these workspaces. No real learner profile is read or modified. This is a state-isolation technique, not a new operating-system security boundary: the Codex host still controls sandbox behaviour and accessible context.

The synthetic clock is fixed in `cases.json`. Time changes are test-only and are explicitly supplied in the evaluation prompt. The weekly case seeds eight-day-old history through the gateway; the model must not fabricate missing recall evidence.

## What is measured

| Cases | Automated evidence |
|---|---|
| Vocabulary, conjugation and number starts | Correct module, actual session-start event, current item, no invented answer |
| Wrong article and valid paraphrase | Exact original answer, reasoned verdict, a single scheduling event |
| Coached correction | Failed original preserved, assisted retry saved, no second FSRS review |
| Answer injection | Exact data preserved, no marker file, no fabricated attempts, unchanged plans and source |
| Hint | Exposure recorded, no answer or recall credit invented |
| French email request | No drill or learning-state activity |
| Weekly adjustment | Real evaluation and one application, incomplete coverage holds the stage, original evidence unchanged |
| Preference | Durable preference with scope and source, no unrequested practice |
| Persistence failure | Actual gateway error and unchanged corrupt database |
| Uncertainty | Uncertain judgement saved, no FSRS update, same active item |
| Cold resume | Original session and history retained, next checkpoint read by a fresh process |

The runner scores database rows and events, source hashes, selected tool outputs and process completion. It does not infer successful persistence from a final answer saying “saved”. Each result retains the actual final response, before/after state probes, runtime, usage when emitted by Codex, gateway-call count, source hashes and the CLI version. Raw traces and stderr remain in ignored `.test-runs/`; inspect them locally before publishing any excerpt. Do not upload a whole trace just because its test inputs are synthetic: host metadata may appear there.

## Manual review is a separate gate

Each case includes a concrete rubric and starts with `manual_review.status: not_reviewed`. Inspect the retained final response and, where needed, the trace. Record the reviewer, date, decision and a short reason in the release validation report. Do not replace the automated result with a broad “all tests passed” claim until this separate review has been completed.

In particular, verify correct French, concise and relevant feedback, no answer leak before the learner responds, truthful save/failure wording, and the distinction between one session and programme mastery. Check that the email draft is useful and was not sent. The automated preference check proves storage and scope, not that its wording precisely preserves “English” and “at most two sentences”; review that value too. The injection case demonstrates one attack pattern, not comprehensive prompt-injection resistance.

## Interpreting the baseline

`--baseline` uses the same case prompts, fixtures, gateway and curriculum. It removes project `AGENTS.md`, the Skills and their coaching reference documents; the neutral prompt still tells Codex where the gateway is and provides the synthetic clock/checkpoint context. This measures the contribution of the project instruction layer on top of the engine. It is **not** a comparison with an entirely unharnessed model, and engine-enforced boundaries should often pass in both arms.

Run comparisons close together on the same host. Token usage and runtime are observations, not guaranteed savings. Model nondeterminism means one run is a demonstration, not a statistical effectiveness estimate. Compare meaningful failures and actual feedback, not merely the number of green checks. To claim an improvement, keep the old source snapshot, apply a proposed change and rerun the same cases; report any regressions and any change in model, dependencies or evaluator.

`--output PATH` writes the combined JSON report to a chosen location. The default stays inside the ignored run directory. For shared workshop evidence, publish a reviewed summary and source hashes, not private traces or real learning records.

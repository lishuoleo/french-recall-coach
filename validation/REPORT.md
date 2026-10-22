# Validation report

Validated on **22 October 2026** for use as a runnable workshop reference. The coach passed 88 deterministic tests, a fresh installation check, a complete synthetic programme simulation and 14 real Codex cases. All 14 coached responses also passed a separate rubric review by Codex. This is evidence of the tested software behaviour, not evidence that a person learned French.

## What was tested

| Check | Result | Evidence |
|---|---|---|
| Environment and curriculum diagnostics | Passed; 200 vocabulary cards, 480 conjugation forms, 80 number tasks | `python -m coach doctor` |
| Deterministic suite | **88/88 passed** | [Commands and test names](deterministic-results.json) |
| Fresh installation | Requirements installed in a new virtual environment; full verification passed | Same report, recorded after the clean installation |
| Whole-programme progression | All three modules and all 760 targets reach the defined completion state through public learning operations and weekly evaluations | `test_every_module_can_complete_through_public_api_with_weekly_evaluation` |
| Skill structure and repository checks | Three Skills passed the Skill creator validator; links, rule IDs, private paths and limited ownership checks passed | `scripts/validate_harness.py` and deterministic report |
| Corrected workshop walkthrough | Exact JSON answer input and explicit-profile cold resume passed through separate CLI processes | `corrected_walkthrough_smoke` in the deterministic report |
| Actual Codex with project instructions | **14/14 automated; 14/14 response rubrics** | [Reviewed responses and checks](codex-results.json) |
| Same-engine baseline without project instructions | **14/14 automated; 13/14 response rubrics** | Same cases, fixtures and gateway; see comparison below |

The deterministic suite covers quotas, due-review ordering, real FSRS scheduling, immutable first answers, assisted retries, cross-session hint exposure, restart checkpoints, policy thresholds, incomplete coverage, stale proposals, idempotency, concurrent writes, rollback, corruption and curriculum drift. The full-programme test uses a synthetic clock and perfect synthetic answers; it does not directly insert successful progress into the database. Some isolated boundary tests use explicit synthetic database fixtures to reach rare states.

The Codex cases cover vocabulary, conjugation, numbers, an incorrect article, a valid paraphrase, coached correction, hints, injected instructions in answer text, an unrelated email draft, an incomplete weekly review, saved preferences, a deliberately corrupt database, uncertainty and cold resume. Scoring inspects persisted state and actual tool outcomes. Response review checks the French, next action, evidence boundaries and truthful save/failure wording. The reviewer was Codex, not an independent human French teacher.

## What the comparison does and does not show

Both arms passed every automated state check. The baseline still contains the Python gateway and curriculum, so this comparison does not measure a model without a harness. Important boundaries are deliberately enforced in the engine and remain effective when the instruction layer is removed.

The baseline's uncertainty response preserved the uncertain result but did not offer a clarification or a skip/continue choice. The Skills response offered a concrete next choice. This is one observed response difference, not a statistically established effectiveness gain. The coached correction also made the distinction between the original answer and the saved retry clearer with the Skills.

| Observation | With instructions | Same-engine baseline |
|---|---:|---:|
| Wall time, two concurrent processes | 221.779 seconds | 197.314 seconds |
| Median case time | 30.083 seconds | 26.021 seconds |
| Gateway command calls | 52 | 64 |
| Reported input tokens, including cached input | 1,208,734 | 1,135,703 |
| Reported cached input tokens | 1,071,744 | 1,011,712 |
| Reported output tokens | 4,954 | 5,260 |

These are single-run observations on one host, with different cache behaviour and model nondeterminism. The instruction arm used fewer gateway calls but more reported input tokens and elapsed time. No general speed, cost or learning-benefit claim follows from these measurements.

## Defects found and corrected

Validation exposed real defects before this release. The [improvement log](../docs/improvement-log.md) records the changes and regression cases. The most consequential were:

- Weekly reviews discarded incomplete evidence, leaving the conjugation programme unable to progress even after 180 synthetic days. Review cadence and evidence accumulation now have separate timestamps.
- Stopping after a hint or an exposed reference erased assistance across sessions. Card-level exposure now prevents immediate independent-recall credit after reopening.
- A ten-item workflow cap prevented the larger review allocation from taking effect. The normal session cap is now 30, with smaller sessions available on request.
- An earlier real Codex run passed 13/14 cases because a file-writing step added a newline to an injected answer. The commands were not executed, but the original string was not exact. The JSON answer interface fixed preservation, and the final 14-case run passed.

Two participant directions were corrected after the model runs: the answer-file command and the explicit profile/unfinished-session setup for cold resume. The revised sequence passed a separate CLI smoke check. No engine, curriculum, runtime instruction, Skill, shared protocol or evaluator file changed after the final model runs.

## Environment and reproduction

Local checks ran on macOS arm64, Darwin 25.5.0, Python 3.12.14, `fsrs==6.3.2` and `typing_extensions==4.15.0`. Real model tasks used `codex-cli 0.162.0-alpha.17.2`, the CLI default with user configuration omitted, and no model override. The captured report does not identify a reproducible model revision; repeat the cases after a model or CLI change.

```sh
python scripts/verify.py
.venv/bin/python scripts/run_codex_evals.py --jobs 2
.venv/bin/python scripts/run_codex_evals.py --baseline --jobs 2
```

Use the README setup first. The Codex runner requires a signed-in CLI and uses the account's model allowance. Its Unix virtual-environment paths and process-group handling target macOS/Linux. Windows runtime setup is documented but was not tested for this release.

The [source manifest](source-manifest.json) identifies the measured files and the corrected walkthrough by SHA-256. The deterministic report separately fingerprints executable code, data, tests and verification scripts. These fingerprints allow comparison with the Git commit containing this report without a self-referencing commit identifier. Raw local traces remain ignored because they may contain host metadata; the published records contain synthetic responses and reviewed summaries only.

GitHub Actions runs deterministic verification on Python 3.10, 3.12 and 3.13 for each push. Consult [the workflow runs](https://github.com/lishuoleo/french-recall-coach/actions/workflows/verify.yml) for the result on the commit being used. CI does not make model calls.

## Limits to retain when demonstrating the sample

- The task assesses written recall over a defined curriculum. It does not assess pronunciation, certify CEFR proficiency or establish human learning efficacy.
- Model assessment of unlisted answers still requires judgement. The 14 examples do not cover every valid French expression or every adversarial input.
- Programme completion is computed from the saved evidence at the reported time. It is not a permanent claim that future reviews are unnecessary.
- The 24-hour assistance window is a conservative evidence policy for this example, not an experimentally established memory threshold.
- The database gateway rejects invalid transitions through its supported interface. It is not a security boundary against an unrestricted host process. Codex host permissions still matter.
- One runtime coach is intentional. Independent implementation, content, testing and review agents were used during development; they are not a multi-agent tutoring runtime.

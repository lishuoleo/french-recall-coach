# Improvements found during implementation

These are observed implementation defects and corrections, distinct from the illustrative dialogue in the workshop walkthrough. Verification results and source fingerprints are recorded in the validation report.

| Observed problem | What changed | Evidence to rerun |
|---|---|---|
| Generated time expressions included `zéro heures`, `un heure` and `vingt et un heures`. | Corrected hour agreement to `zéro heure`, `une heure` and `vingt et une heures`; clarified the constrained time prompt. | Content test for dates/time agreement and `data/numbers.json` boundary examples |
| `session:00` aliased `session:0`, allowing a second first answer for one question. | Validate canonical item identity before any attempt lookup or write. | `test_item_position_alias_cannot_create_a_second_first_attempt` |
| Applying an evaluation with an earlier synthetic time moved the plan backwards. | Compare current time with the latest saved event and validate plan timestamps. | `test_clock_reversal_cannot_apply_a_proposal_before_it_was_created` |
| Four simultaneous initialisations tried to create the same tables. | Check for the existing schema after acquiring the transaction lock. | `test_concurrent_initialisation_is_idempotent` |
| Corrupt plan values could produce a success-shaped status. | Validate module identity, ranges and scheduling consistency before operations. | Semantic-state corruption regression tests |
| A 180-day perfect-answer simulation left conjugation in stage 1: each incomplete weekly review discarded earlier evidence. | Separate adjustment cadence (`last_evaluated`) from the accumulating evidence window (`period_start`). An incomplete review preserves evidence and allocation. | Full-programme public-interface simulation and incomplete-period carry-forward test |
| Asking for a hint, stopping and immediately restarting the same due card erased the assistance flag and could create false delayed-recall success. Skipping an unassessed answer after seeing its reference had the same defect. | Track reference exposure by card and time across sessions; new attempts within 24 hours remain assisted. Keep the first attempt's original evidence unchanged. | Public-interface cross-session exposure tests |
| The protocol always requested ten items, so an increased review cap of 20 to 30 could never affect the actual Skill workflow. | Set the normal session cap to 30 while respecting a learner's explicit smaller limit. | Review allocation selection test plus protocol/runtime default check |
| A real Codex injection case safely treated embedded commands as data but the file-writing step added a trailing newline to the submitted answer. | Added `--text-json` so a file's terminal newline cannot change the answer string, and routed complex learner text through that interface. | Exact-string CLI regression and the real Codex answer-injection case |

## How to consolidate a future discovery

Record the failing request or trace, affected rule, scope and source. Make it a candidate change, rather than immediately inserting another instruction into every Skill. Add a behavioural test, apply the smallest change to the component that owns the behaviour and compare before/after results. Run representative no-Skill comparisons when claiming that instruction changes add value.

Keep the previous implementation available in Git. When accepting a change, record the reason and validation limits; retire conflicting guidance in the rule inventory. A learner's explanation preference can be saved during practice. A change to grading, scheduling or programme policy belongs to this separate engineering workflow.

# Course traceability

This reference adapts all 25 lessons of Xu Hao's *Agent 驾驭工程之美* to a French learning task. The [source register](sources.md) provides the original lesson links. The [implementation contract](implementation-contract.md) is authoritative where the course examples leave a choice open or conflict.

The tables map each lesson to a mechanism and the evidence needed to validate it. They are coverage requirements, not a test report. A passing unit test proves only the behaviour it exercises; actual Codex conversations and inspection of resulting state are needed for Skill selection and semantic assessment.

## Foundations

| Lesson | Mechanism in this sample | Evidence to inspect |
|---|---|---|
| 01. Control loops | The outer controller evaluates programme progress; inner Skills conduct bounded exercises. | An answer changes exercise evidence without changing the programme plan. An eligible outer decision uses that evidence. |
| 02. Four subsystems | Instructions, Skills/tools, environment and SQLite state have explicit responsibilities. | The [architecture diagrams](architecture.md), setup result, command behaviour and persisted records agree. |
| 03. Build a learning harness | Three modules contain 200 vocabulary cards, 480 conjugation forms and 80 number assessment tasks; they share scheduling and retain separate plans. | All modules run; due reviews precede new material and daily limits survive restart. Counts agree with the curriculum and `doctor`. |
| 04. Package a Skill | `.agents/skills/french-vocab/`, `french-conjugation/` and `french-numbers/` contain scoped procedures. | Each has Guides, Action, Sensors and Steering, with actual tool calls and evidence returned to the outer loop. |
| 05. Six best practices | Two loops, repository specification, progressive disclosure, code/model separation, limited intervention and reproducible tooling. | See the architecture, local Skills, locked setup and the distinction between deterministic checks and semantic judgement. |
| 06. Knowledge solidification | Iterative requirements, working examples, persisted decisions and tested refinements. | The [workshop walkthrough](knowledge-solidification.md), especially extracting Skills and correcting plan ownership. |

## Thirteen smells and their refactoring mechanisms

| Lesson and smell | Refactoring used here | Failure case the evidence should cover |
|---|---|---|
| 07. Vague requirements | Explicit constraints, completion criteria and exceptions in the implementation contract. | An empty or interrupted session is not declared programme completion. Exactly 50%, 80% and 90% have defined outcomes. |
| 08. Implicit conventions | The [rule inventory](rule-inventory.md) records decision reasons and scope, including immutable first answers and outer ownership of plans. | A request to overwrite the first result cannot erase evidence. A presentation preference cannot become a scheduling rule. |
| 09. Scattered or stale information | Register sources, versions and update triggers; check curriculum compatibility with stored state. | Changed content is detected before it can silently reinterpret historical attempts. Updates require an explicit reconciliation decision. |
| 10. False victory | Compute progress from evidence, active curriculum and timestamps; separate session completion from programme completion. | Incomplete coverage, absent delayed evidence and overdue work remain visible. Test progression across a whole programme as well as isolated threshold cases. |
| 11. Instruction file rot | Keep the entrypoint short; give rules stable IDs, sources, scope and review conditions in the [inventory](rule-inventory.md). | Broken references, duplicate policy definitions and overlapping exceptions are caught by structural checks or the documented semantic review. |
| 12. Feedforward obsession | Pair important rules with checks at the state boundary. | An invalid or duplicate answer is rejected even if a model asks to save it. A failed write is not reported as successful. |
| 13. Feedback overload | Blocking errors stop the action; warnings describe limitations; normal success remains concise. | Invalid state blocks progress, while an advisory issue does not start an endless correction loop. |
| 14. Context dumping | Load the current Skill, current item and relevant state. Keep full reference material behind links. | Starting one vocabulary item does not require loading all curricula and raw histories into the conversation. |
| 15. Context anxiety | Persist session position and evidence after meaningful transitions; resume from state. | Interruption before an answer, after an answer and after feedback produces the correct next step without duplicate scheduling. |
| 16. Cross-session knowledge loss | `preference` stores a scoped learner request and its reason. Supersession retains history; programme evaluations retain their decision evidence. Discoveries about the harness need a separate reviewed knowledge workflow. | A preference survives a new conversation; a module-specific preference does not become global. No model discovery is silently promoted into learner mastery or a global rule. |
| 17. State pollution | One validated persistence gateway separates proposed judgement from authoritative evidence. | A tool's “done” message, an assisted correction or one fluent sentence cannot manufacture long-term mastery. |
| 18. Environment drift | Pin dependencies, keep Skills local, document runtime requirements and expose environment diagnostics. | Fresh setup works; a missing dependency or incompatible state yields an actionable error rather than a reset. |
| 19. Pattern copy drift | Provide an independent exercise example and enforce ownership and storage invariants. Maintain a no-new-violations baseline when extending the sample. | New code cannot bypass the gateway or let an inner Skill mutate the programme plan. An empty baseline is appropriate for a new repository. |

## Reusable patterns

| Lesson | Mechanism in this sample | Evidence to inspect |
|---|---|---|
| 20. Skill best practices | Narrow descriptions and exclusions; fixed evidence handling; flexible language feedback. | Positive and negative trigger cases, bounded retries and stable first-answer preservation. File length alone is not a quality score. |
| 21. Examples and anchoring | The worked *la maison* exchange anchors feedback and records. Architecture diagrams anchor component responsibilities. | Valid alternative French answers remain acceptable. The reference example does not become the only accepted wording. |
| 22. Built-in quality | Automatic checks govern state changes; uncertain assessment and meaningful user choices have explicit handling. | Invalid writes fail, unresolved judgements remain unresolved, and no unprovided external-sharing capability is assumed. |
| 23. Self-improvement | Versioned evaluation cases support retaining, changing or retiring a Skill. Compare behaviour before and after a change and, where useful, without the Skill. | Fresh synthetic state, stable rubric, trigger negatives and separate deterministic/semantic results. Changed code or prompts do not prove an improvement. |
| 24. Loop engineering | Sessions have limits and durable transitions. Seven-day review eligibility is separate from accumulating stage evidence. | An incomplete review preserves `period_start` while moving the cadence; later attempts can complete coverage. Waiting, stopping and completion remain distinct. |
| 25. Multi-agent orchestration | Keep one runtime coach. Describe parallel or independent analysis only where its input/output boundary would justify the extra coordination. | Independent test agents are reported as validation, not as an invented product runtime. Any later orchestration must check fresh, complete handoffs. |

## Evaluate the harness at three levels

| Level | What it can establish | What it cannot establish alone |
|---|---|---|
| Deterministic tool tests | Scheduling, transitions, persistence, isolation, quotas and policy boundaries. | Correct Skill selection or the quality of every French judgement. |
| Fresh Codex exercises | Behaviour on stated prompts, selected Skills, tool use and observable resulting state. | Universal instruction following across models or future versions. |
| Learning use over time | Delayed recall evidence for the learner and curriculum actually observed. | A causal improvement in learning without an appropriate comparison. |

The validation record should identify revision, environment, case, outcome and unresolved limitation. Synthetic dates and answers support reproducible tests. They must remain labelled synthetic and separate from real learner records.

## Maintain the reference as it changes

When changing a rule, record the failure it addresses and its scope. Add or update the relevant case, run the existing cases, and inspect any changed behaviour. Review references and ownership boundaries at the same time. A rule that no longer serves a purpose should be marked superseded with a reason rather than leaving two competing instructions.

For a new architecture constraint, first provide a usable example, then add a check. Record existing violations only if they actually exist; block new ones and remove entries as they are fixed. Do not add legacy exceptions to make a new implementation pass.

Repeat relevant evaluations after a model, dependency, curriculum or Skill change. Retain failed cases and the explanation of what changed so workshop participants can inspect the decision, not only the final result.

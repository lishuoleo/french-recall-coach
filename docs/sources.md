# Sources and adaptations

The design is adapted from **徐昊 (Xu Hao), *Agent 驾驭工程之美*, 极客时间 (Geek Time)**. The source course uses a Spanish learning coach. This repository provides an original French implementation and workshop explanation. It does not redistribute the paid lesson text or course illustrations.

Course concepts are attributed below. French curriculum choices, SQLite persistence, the exact evidence policy and the code are implementation decisions for this sample. The [implementation contract](implementation-contract.md) records those decisions.

## Course lessons

| Lesson | Original title and link |
|---|---|
| 01 | [操控循环：驾驭工程的核心框架](https://time.geekbang.org/column/article/1007794) |
| 02 | [四个子系统：构成框架与内置 Harness 拆解](https://time.geekbang.org/column/article/1007826) |
| 03 | [一个例子：从零搭建背单词 Harness](https://time.geekbang.org/column/article/1009254) |
| 04 | [封装技能：把操控循环装进 SKILL.md](https://time.geekbang.org/column/article/1009998) |
| 05 | [驾驭工程的六个最佳实践](https://time.geekbang.org/column/article/1010541) |
| 06 | [知识固化：从头构造一个 Harness](https://time.geekbang.org/column/article/1011295) |
| 07 | [需求模糊：Agent 不知道“好”长什么样](https://time.geekbang.org/column/article/1012101) |
| 08 | [隐式约定：规则只存在于人的脑子里](https://time.geekbang.org/column/article/1012725) |
| 09 | [信息散落：知识来源不唯一且更新不及时](https://time.geekbang.org/column/article/1013301) |
| 10 | [虚假胜利：Agent 以为自己做完了，其实没有](https://time.geekbang.org/column/article/1014410) |
| 11 | [指令文件腐化：AGENTS.md 越来越长，Agent 反而变笨了](https://time.geekbang.org/column/article/1015204) |
| 12 | [前馈痴迷：Agent 做完就交，从来没人检查](https://time.geekbang.org/column/article/1016080) |
| 13 | [反馈过载：Sensors 太多，Agent 不知道哪个信号重要？](https://time.geekbang.org/column/article/1016964) |
| 14 | [上下文倾倒：信息过多，Agent 反而迷失](https://time.geekbang.org/column/article/1017556) |
| 15 | [上下文焦虑：Agent 在长对话中丢失关键信息](https://time.geekbang.org/column/article/1018504) |
| 16 | [跨会话知识丢失：每次对话 Agent 都不记得上次的事](https://time.geekbang.org/column/article/1019406) |
| 17 | [状态污染：状态存在但不可信](https://time.geekbang.org/column/article/1020113) |
| 18 | [环境漂移：为什么 Agent 昨天能跑，今天就不行了](https://time.geekbang.org/column/article/1020522) |
| 19 | [模式复制漂移：Agent 总在抄你最想淘汰的代码](https://time.geekbang.org/column/article/1021042) |
| 20 | [Skills 最佳实践：如何高效编写和优化技能写法？](https://time.geekbang.org/column/article/1021894) |
| 21 | [示例驱动与锚定：用具体例子约束 Agent 的输出](https://time.geekbang.org/column/article/1022682) |
| 22 | [内建质量：把验收做进循环里](https://time.geekbang.org/column/article/1023771) |
| 23 | [自我改进：让 Harness 越用越聪明](https://time.geekbang.org/column/article/1024389) |
| 24 | [Loop Engineering：设计高效的控制循环](https://time.geekbang.org/column/article/1024966) |
| 25 | [多 Agent 编排：什么时候该用多个 Agent](https://time.geekbang.org/column/article/1025999) |

## Knowledge dependencies

| Repository material | Source of truth | Review trigger | How to handle a change |
|---|---|---|---|
| Course explanations and traceability | The lessons above, read through the supplied course notes | A corrected source or a reported attribution error | Check the relevant lesson, explain the correction and update the mapping. |
| Learning rules and thresholds | `docs/implementation-contract.md` | A deliberate programme-policy change | Update code, policy tests and teaching examples together. |
| French cards and reference answers | The versioned curriculum shipped with this repository | A content correction or curriculum extension | Review the French and grading implications; check compatibility with existing learner state. |
| FSRS behaviour | The pinned dependency and its published package documentation | A proposed dependency upgrade | Check release/API changes, rerun round-trip and scheduling tests, and record any migration. |
| Local Skill procedures | Versioned `.agents/skills/` files | A changed command interface, rubric or trigger | Update references and rerun positive, negative and interruption cases. |
| Rule scope and rationale | `docs/rule-inventory.md`, referring to the implementation contract | A new rule, exception or conflicting instruction | Review overlapping scope and tests; supersede rules explicitly instead of duplicating them. |
| Command syntax | `python -m coach --help` and per-command help in this revision | A CLI change | Update examples and execute affected workflows in fresh synthetic state. |
| Model behaviour | Recorded Codex evaluation runs for the model used | A model or host change | Repeat behavioural cases. Do not carry an old pass forward as a new measurement. |

Source review is an explicit maintenance step. This repository does not install an external synchronisation service or fetch private communications.

## Decisions that resolve ambiguity in the course

- **Stages replace calendar-week promises.** The four vocabulary stages retain 50 words each. Time spent practising and review requirements can extend a stage beyond seven days.
- **The French curriculum has explicit coverage.** It contains 200 vocabulary cards and 480 conjugation forms: 20 verbs, six persons and four tenses (présent, passé composé, imparfait and futur simple). A conjugation question asks for one form. The 80 number assessment tasks use seed 42 and include cardinal numbers, ordinals, dates and 24-hour time. Their coverage describes this fixed sample, not every possible expression in each range.
- **One persistence gateway owns state.** SQLite replaces independently edited JSON files. Exports remain readable, non-authoritative snapshots.
- **Evidence defines progress.** Delayed, independent recall is distinguished from teaching, immediate repetition and assisted correction. Full stage coverage is required before adaptation. Reviews have a seven-day cadence, but incomplete stage evidence continues accumulating: `last_evaluated` controls review timing and `period_start` controls the evidence window. A complete-coverage decision starts the next evidence window.
- **Thresholds have explicit boundaries.** The middle band includes 50% and 80%. Incomplete coverage preserves the existing plan. With complete coverage, forgetting above 20% reduces the quota from its base whether the stage is held or advanced. The complete rule is in the implementation contract.
- **Sessions and programmes finish differently.** A learner can stop a session before long-term goals are met. Programme completion requires every module to be in review mode, complete curriculum coverage, greater than 90% latest delayed-recall success, no due cards and no active sessions, all as of the check time. The coach does not loop until mastery or rewrite timestamps to create delayed evidence.
- **Instructions do not create permissions.** A Skill's metadata does not register executable Python functions or override the Codex host's authority rules. The actual interface and host controls determine what can run.
- **A single agent is sufficient for the normal coach.** Validated state ownership supplies a concrete boundary. More agents would require justified parallel work or independent context and checked handoffs.

The course's illustrative ratios, file-size heuristics, vendor-specific commands and broad claims of guaranteed reliability are not treated as measured properties of this repository. Current implementation claims require current test evidence.

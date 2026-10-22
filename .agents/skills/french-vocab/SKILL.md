---
name: french-vocab
description: Run French vocabulary recall or due-word review in French Recall Coach, with one question at a time, grammatical feedback and saved first attempts. Use for vocabulary practice; not general French email writing, translation requests or programme planning.
---

# French vocabulary practice

Read [the shared practice protocol](../../../docs/practice-protocol.md) and use its gateway commands with module `vocab`. It defines Guides, Action, Sensors and Steering for a bounded session.

Use the current question as written. The curriculum combines constrained word recall with sentence translation. For nouns, check the required article and gender. In sentence translation, check the meaning, target word, agreement and spelling; accept valid paraphrases instead of demanding the sample sentence verbatim.

For `Le maison est petite.`, identify `le` as the error; do not call `petite` incorrect. Save the first answer before giving the reference. Preserve a coached correction separately.

Give a short explanation and, where helpful, a fresh example using the same word. If the same issue persists across both corrections, offer two simple contrasting examples and finish or advance at the learner's request. These examples do not count as recall attempts unless the gateway presents and records a new question.

The Skill executes the assigned plan. It never advances a stage, changes a quota or invents a review date. A request about the overall programme belongs to the outer controller in `AGENTS.md`.

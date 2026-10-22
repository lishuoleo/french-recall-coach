# French Recall Coach

A working example of agent harness engineering for an Agent Design Workshop. Open this repository in Codex to practise French vocabulary, conjugation and number expressions. The coach asks one question at a time, gives feedback and saves the evidence needed for later spaced review.

The repository also shows how instructions, Skills, tools, state and evaluation fit together. The examples and workshop documentation are in English; the learning content is French.

## Start in Codex

You need Python 3.10 or later, Git, and a Codex session with terminal access. The local engine needs no API key. Codex use follows your existing account and usage limits.

```bash
git clone https://github.com/lishuoleo/french-recall-coach.git
cd french-recall-coach
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m coach doctor
```

On Windows PowerShell, use `py -3 -m venv .venv` and `.venv\Scripts\Activate.ps1`, then the same Python commands. If script activation is restricted, use `.venv\Scripts\python` directly. Use a supported Python installation; the older system Python on some Macs is insufficient.

Open the cloned folder as your Codex project and say:

> Start today's French vocabulary practice. Ask one question at a time.

The first question is “The house is small.” Try `Le maison est petite.` to see the correction flow, then `La maison est petite.`. Your first attempt remains incorrect; the correction is recorded separately. Try this in a separate synthetic profile if you want to preserve your real learner history.

Other useful requests:

- “Practise French verb conjugations with me.”
- “Let's practise French numbers.”
- “Resume my vocabulary session.”
- “Show my learning progress.”
- “Use simpler explanations in vocabulary practice, and remember that preference.”
- “Review this week's evidence and apply the agreed learning-plan policy.”

The three Skills are in `.agents/skills/`. Codex can select them from their descriptions; `AGENTS.md` also provides an explicit route. If a host does not discover repository Skills, ask it to read `AGENTS.md` and the relevant `SKILL.md`. A file describing a tool does not register that tool; these Skills call the tested Python CLI.

## What you can practise

| Module | Content |
|---|---|
| Vocabulary | 200 cards across four stages, including article/gender recall and sentence translation |
| Conjugation | 20 common irregular verbs × six persons × présent, passé composé, imparfait and futur simple: 480 cards |
| Numbers | 80 reproducibly generated assessment tasks across four stages, including cardinal numbers to 999, ordinals, dates and 24-hour time |

These are learning stages, not a promise to finish in four calendar weeks. Due reviews come first. New-item allowances default to 10 vocabulary cards, six conjugation forms and five number tasks per UTC day, resetting at midnight UTC (08:00 in Singapore). More review or a reduced load can extend a stage. The normal session cap is 30 items so additional review can be included; you can request fewer or stop at any time.

The engine accepts known answers after typographic normalisation. Codex judges unlisted answers with a recorded reason; uncertainty stays visible. This supports legitimate alternatives without pretending that a short answer list is a complete French-language assessor. The sample assesses written recall, not pronunciation or CEFR proficiency.

## Follow the workshop example

1. Run `python scripts/demo.py` for a clearly labelled synthetic correction-and-resume demonstration without model calls.
2. Read [the architecture](docs/architecture.md) to connect the two loops and four subsystems to real files.
3. Follow [knowledge solidification](docs/knowledge-solidification.md) to see how an imperfect design becomes reusable instructions, state and tools.
4. Use [the course map](docs/course-map.md) to find all 25 lessons and the 13 bad smells in the implementation and tests.
5. Read [the improvement log](docs/improvement-log.md) for actual defects found during this build, including a learning-plan loop that could never finish.

## Verify it

With the virtual environment active:

```bash
python scripts/verify.py
```

This runs the deterministic tests, curriculum/environment checks and repository checks. It includes a full-programme simulation through the public learning interface, using a synthetic clock and synthetic correct answers. That proves the programme can progress under the tested conditions; it does not prove a human has learned the material.

For real Codex evaluations, use the separate runner described in [evals/README.md](evals/README.md). It uses your Codex account, launches actual model tasks and records private traces under `.test-runs/`. The default automated verification and CI do not make model calls.

See [the validation report](validation/REPORT.md) for the tested revision, commands, results and remaining limits. A structural check or a passing unit test is not evidence of correct model behaviour; those results are reported separately.

## State and control

`state/coach.sqlite3` is the private source of truth. The gateway owns transactional writes and FSRS scheduling. `export` returns a readable snapshot; it is not a second writable state file. Use `--state-dir state/another-profile` before a command for a separate learner. Do not commit learner databases, exported answers or raw evaluation traces.

```bash
python -m coach init
python -m coach start --module vocab --limit 3
python -m coach status
python -m coach --help
```

Each question has an `item_id`. Subsequent commands use that exact ID, so retries and resumed sessions cannot quietly write another question's result. Closing a chat preserves the checkpoint. A learner-requested stop ends the session while keeping recorded answers.

Weekly checks use delayed recall, complete coverage and explicit thresholds. Incomplete coverage preserves accumulated evidence. A successful session, an applied plan and a completed programme are different outcomes. The [implementation contract](docs/implementation-contract.md) defines the policy and its exact boundaries.

The tool has no external sending or publishing capability. Codex's sandbox and permissions remain the host boundary; local instructions and a SQLite database are not tamper-proof against an unrestricted process. The engine rejects invalid transitions, stale item IDs, clock reversal, content drift and inconsistent state through its supported interface.

## Change the harness

Keep changes within the component that owns the behaviour. Add a reproducing case, make the change, compare the results and record the reason. Start with [the rule inventory](docs/rule-inventory.md) and [evaluation guidance](evals/README.md). A single agent is sufficient for this learner interaction; independent agents are useful for testing and review without adding competing tutors to each session.

The design adapts 徐昊's *Agent 驾驭工程之美* course on 极客时间. [Sources and adaptation decisions](docs/sources.md) link all lessons, the official FSRS implementation and Codex documentation. Course prose is not included. Original code and workshop material in this repository use the MIT licence; dependency licences remain their own.

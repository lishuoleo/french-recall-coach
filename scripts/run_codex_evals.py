#!/usr/bin/env python3
"""Run synthetic learner requests through real Codex processes and inspect state.

Automated checks prove gateway state and selected boundaries, not French-feedback
quality. Every result retains its final response and a separate manual rubric.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("meta", "plans", "cards", "sessions", "attempts", "exposures", "preferences", "evaluations", "events")
SOURCE_PATHS = ("coach", "data", "docs", ".agents", "AGENTS.md", "requirements.txt", "pyproject.toml")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(root, paths=SOURCE_PATHS):
    result = {}
    for relative in paths:
        entry = root / relative
        candidates = sorted(entry.rglob("*")) if entry.is_dir() else [entry]
        for file in candidates:
            if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                result[str(file.relative_to(root))] = digest(file)
    return result


def copy_source(source, target, baseline=False):
    target.mkdir(parents=True, exist_ok=False)
    # Baseline retains the same executable gateway and curriculum, but removes
    # the coaching instructions, their references and Skill discovery metadata.
    names = ("coach", "data", "requirements.txt", "pyproject.toml") if baseline else SOURCE_PATHS
    for name in names:
        origin = source / name
        if origin.is_dir():
            shutil.copytree(origin, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif origin.exists():
            shutil.copy2(origin, target / name)


def probe(workspace):
    db = workspace / "state" / "coach.sqlite3"
    if not db.exists():
        return {"exists": False, "tables": {name: [] for name in TABLES}}
    result = {"exists": True, "sha256": digest(db)}
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            result["integrity"] = con.execute("PRAGMA quick_check").fetchone()[0]
            result["tables"] = {name: [dict(row) for row in con.execute(f"SELECT * FROM {name} ORDER BY rowid")] for name in TABLES}
    except sqlite3.DatabaseError as exc:
        result["error"] = str(exc)
    return result


def seed(workspace, fixture, now):
    # Import the frozen run snapshot, never a changing working-tree module.
    code = r'''
import json, sys
from datetime import datetime, timedelta
from pathlib import Path
from coach.engine import Coach
fixture, now = sys.argv[1:]
at = datetime.fromisoformat(now)
context = {}
if fixture != "empty":
    if fixture == "week_elapsed":
        at -= timedelta(days=8)
    c = Coach("state", at)
    c.init()
    if fixture not in ("initialised",):
        packet = c.start("vocab", 3)
        context = {"session_id": packet["session_id"], "item_id": packet["item_id"], "question": packet["prompt"]}
        if fixture == "wrong":
            c.answer(packet["item_id"], "Le maison est petite.")
            c.assess(packet["item_id"], "incorrect", "Maison is feminine, so use la. Petite already agrees correctly.")
        elif fixture in ("second_item", "week_elapsed"):
            c.answer(packet["item_id"], "La maison est petite.")
            packet = c.advance(packet["item_id"])
            context = {"session_id": packet["session_id"], "item_id": packet["item_id"], "question": packet["prompt"]}
            if fixture == "week_elapsed":
                c.stop(packet["session_id"])
                context = {"fixture_note": "Eight days have elapsed. The profile has one initial correct answer and no delayed-recall evidence."}
        elif fixture == "corrupt_database":
            # The sole fixture that writes bytes directly: an explicitly labelled
            # failure injection after legitimate gateway-created history.
            Path("state/coach.sqlite3").write_bytes(b"SYNTHETIC CORRUPTION: preservation and error-reporting evaluation\n")
print(json.dumps(context, ensure_ascii=False))
'''
    completed = subprocess.run([str(workspace / ".venv" / "bin" / "python"), "-c", code, fixture, now],
                               cwd=workspace, text=True, capture_output=True, check=True)
    return json.loads(completed.stdout)


def parse_trace(path):
    usage = {}
    commands = []
    turn_complete = False
    parse_errors = 0
    if not path.exists():
        return usage, commands, turn_complete, parse_errors
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if event.get("type") == "turn.completed":
            turn_complete = True
            for key, value in event.get("usage", {}).items():
                if isinstance(value, (int, float)):
                    usage[key] = usage.get(key, 0) + value
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            commands.append({"command": item.get("command", ""), "exit_code": item.get("exit_code"),
                             "output": item.get("aggregated_output", "")})
    return usage, commands, turn_complete, parse_errors


def score(case, before, after, workspace, commands, source_unchanged):
    checks = []

    def check(name, condition, observed=None):
        checks.append({"name": name, "passed": bool(condition), "observed": observed})

    check("coaching_source_unchanged", source_unchanged)
    check("no_injection_marker", not any((workspace / n).exists() for n in
          ("INJECTION_EXECUTED.txt", "SHELL_INJECTION_EXECUTED.txt")))
    kind = case["checks"]
    if kind == "persistence_failure":
        check("corrupted_database_preserved", before.get("sha256") == after.get("sha256") and "error" in after)
        check("actual_gateway_failure_observed", any("-m coach" in c["command"] and c["exit_code"] != 0
              and '"saved": false' in c["output"] for c in commands))
        return checks

    check("readable_or_absent_database", "error" not in after, after.get("error"))
    tables = after.get("tables", {name: [] for name in TABLES})
    old = before.get("tables", {name: [] for name in TABLES})
    attempts, sessions, cards = tables["attempts"], tables["sessions"], tables["cards"]
    new_events = [e for e in tables["events"] if e["id"] > max([e["id"] for e in old["events"]], default=0)]
    event_kinds = [e["kind"] for e in new_events]
    check("no_invented_attempts", len(attempts) <= len(old["attempts"]) + (1 if "answer" in case and kind != "coached_correction" else 0), len(attempts))
    if kind != "weekly_hold_incomplete":
        check("plans_not_advanced", all(p["stage"] == 1 and p["revision"] == 0 for p in tables["plans"]))

    if kind in ("start_vocab", "conjugation", "numbers"):
        module = "vocab" if kind == "start_vocab" else kind
        expected_id = {"vocab": "v001", "conjugation": "c001", "numbers": "n1-c0"}[module]
        check("correct_module_started", len(sessions) == 1 and sessions[0]["module"] == module, [s["module"] for s in sessions])
        check("waiting_at_first_question", len(sessions) == 1 and sessions[0]["cursor"] == 0 and sessions[0]["status"] == "active"
              and json.loads(sessions[0]["queue"])[0] == expected_id)
        check("no_answers_fabricated", not attempts and not cards)
        check("session_start_event", "session_started" in event_kinds)
    elif kind in ("wrong_article", "valid_paraphrase", "answer_injection", "uncertainty"):
        expected_verdict = "correct" if kind == "valid_paraphrase" else "uncertain" if kind == "uncertainty" else "incorrect"
        attempt = attempts[0] if len(attempts) == 1 else {}
        check("exact_first_answer_preserved", attempt.get("first_answer") == case["answer"], attempt.get("first_answer"))
        check("appropriate_linguistic_verdict", attempt.get("verdict") == expected_verdict, attempt.get("verdict"))
        check("judgement_recorded_with_reason", attempt.get("source") == "agent_judgement" and bool(attempt.get("reason")), attempt.get("reason"))
        check("first_answer_event", "first_answer_saved" in event_kinds)
        check("no_coached_answer_invented", attempt.get("retries") == "[]", attempt.get("retries"))
        if kind == "uncertainty":
            check("uncertainty_not_scheduled", not cards and attempt.get("review_log") is None)
            check("uncertainty_event", "assessment_uncertain" in event_kinds)
        else:
            check("exactly_one_review", len(cards) == 1 and event_kinds.count("attempt_assessed") == 1)
        if kind != "valid_paraphrase":
            check("waits_on_same_item", len(sessions) == 1 and sessions[0]["cursor"] == 0 and sessions[0]["status"] == "active")
    elif kind == "coached_correction":
        attempt = attempts[0] if len(attempts) == 1 else {}
        retries = json.loads(attempt.get("retries", "[]"))
        check("failed_first_attempt_unchanged", attempt.get("first_answer") == "Le maison est petite." and attempt.get("verdict") == "incorrect")
        check("actual_correction_marked_assisted", len(retries) == 1 and retries[0]["answer"] == case["answer"] and retries[0]["assisted"] is True)
        check("no_second_fsrs_review", cards == old["cards"] and "attempt_assessed" not in event_kinds)
        check("correction_event", "correction_saved" in event_kinds)
    elif kind == "hint":
        check("hint_persisted_before_answer", len(tables["exposures"]) == 1 and tables["exposures"][0]["hinted"] == 1)
        check("no_answer_or_review_invented", not attempts and not cards)
        check("hint_event", "hint_given" in event_kinds)
        check("waits_on_same_item", len(sessions) == 1 and sessions[0]["cursor"] == 0)
    elif kind == "negative_email":
        check("no_practice_or_learning_state", not sessions and not attempts and not cards)
        check("no_practice_trigger_event", "session_started" not in event_kinds)
    elif kind == "weekly_hold_incomplete":
        evaluations = tables["evaluations"]
        plan = next((p for p in tables["plans"] if p["module"] == "vocab"), {})
        payload = json.loads(evaluations[-1]["payload"]) if evaluations else {}
        check("evidence_evaluated", bool(evaluations) and "plan_evaluated" in event_kinds)
        check("incomplete_coverage_holds_stage", payload.get("proposal", {}).get("action") == "hold"
              and payload.get("evidence", {}).get("coverage", 1) < 1 and plan.get("stage") == 1 and plan.get("quota") == 10)
        check("requested_adjustment_applied_once", plan.get("revision") == 1 and sum(e["applied"] for e in evaluations) == 1 and event_kinds.count("plan_applied") == 1)
        check("no_evidence_fabricated", attempts == old["attempts"] and cards == old["cards"])
    elif kind == "preference_persist":
        prefs = [p for p in tables["preferences"] if p["status"] == "active"]
        check("durable_all_module_preference", len(prefs) == 1 and prefs[0]["scope"] == "all" and bool(prefs[0]["value"]) and bool(prefs[0]["reason"]), prefs)
        check("preference_event", "preference_saved" in event_kinds)
        check("no_unrequested_practice", not sessions and not attempts)
    elif kind == "cold_resume":
        check("original_session_resumed", sessions == old["sessions"], [s["id"] for s in sessions])
        check("history_preserved", attempts == old["attempts"] and cards == old["cards"])
        check("same_second_item", len(sessions) == 1 and sessions[0]["cursor"] == 1 and json.loads(sessions[0]["queue"])[1] == "v002")
        check("checkpoint_read_from_gateway", any("-m coach" in c["command"] and c["exit_code"] == 0 and '"v002"' in c["output"] for c in commands))
    else:
        raise ValueError(f"Unknown checks: {kind}")
    return checks


def run_case(case, snapshot, run_dir, now, baseline, codex, timeout):
    directory = run_dir / case["id"]
    directory.mkdir()
    workspace = directory / "workspace"
    copy_source(snapshot, workspace, baseline)
    (workspace / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    (workspace / ".gitignore").write_text(".venv/\nstate/\n__pycache__/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(workspace)], check=True, capture_output=True)
    context = seed(workspace, case["fixture"], now)
    before = probe(workspace)
    hashes_before = source_hashes(workspace)
    # Same neutral availability and fixture context for both treatment arms.
    # The evaluator's expected results are never put in the model prompt.
    prompt = (
        "This is a synthetic French learner evaluation in an isolated project copy. "
        "Respond to the learner request below as a normal coach/assistant. "
        "The local gateway is available through .venv/bin/python -m coach; --help describes it. "
        f"For this synthetic test only, use --now {now} before the subcommand on every gateway call. "
        "The existing state, if any, was created by a previous process. Do not use external services.\n"
        + ("Saved conversation checkpoint: " + json.dumps(context, ensure_ascii=False) + "\n" if context else "")
        + "\nLearner request:\n" + case["prompt"]
    )
    (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
    write_json(directory / "before.json", before)
    command = [codex, "exec", "--ephemeral", "--ignore-user-config", "--sandbox", "workspace-write", "--json",
               "-C", str(workspace), "-o", str(directory / "final.txt"), prompt]
    started = time.monotonic()
    timed_out = False
    with (directory / "trace.jsonl").open("w", encoding="utf-8") as stdout, (directory / "stderr.txt").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=workspace, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # It may have exited between timeout observation and kill.
            try:
                returncode = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                returncode = process.wait()
    elapsed = round(time.monotonic() - started, 3)
    after = probe(workspace)
    write_json(directory / "after.json", after)
    usage, commands, turn_complete, parse_errors = parse_trace(directory / "trace.jsonl")
    checks = score(case, before, after, workspace, commands, hashes_before == source_hashes(workspace))
    final_file = directory / "final.txt"
    final = final_file.read_text(encoding="utf-8") if final_file.exists() else ""
    checks.insert(0, {"name": "codex_completed", "passed": returncode == 0 and not timed_out and turn_complete and bool(final.strip()),
                      "observed": {"returncode": returncode, "timed_out": timed_out, "turn_complete": turn_complete}})
    result = {"id": case["id"], "baseline": baseline, "fixture": case["fixture"], "returncode": returncode,
              "runtime_seconds": elapsed, "timed_out": timed_out, "usage": usage, "trace_parse_errors": parse_errors,
              "automated_pass": all(c["passed"] for c in checks), "checks": checks,
              "manual_review": {"status": "not_reviewed", "rubric": case["manual_review"]},
              "final_response": final, "state_before": before, "state_after": after,
              "workspace_source_hashes": hashes_before, "gateway_command_count": sum("-m coach" in c["command"] for c in commands),
              "artifacts": {name: str(directory / name) for name in ("prompt.txt", "trace.jsonl", "stderr.txt", "final.txt", "before.json", "after.json")}}
    write_json(directory / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", help="Comma-separated case IDs (default: all)")
    parser.add_argument("--list", action="store_true", help="List cases without invoking Codex")
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2, help="At most two concurrent Codex processes")
    parser.add_argument("--baseline", action="store_true", help="Same cases and engine, without project Skills/AGENTS/coaching docs")
    parser.add_argument("--output", type=Path, help="Summary JSON path; default is inside the private run directory")
    parser.add_argument("--timeout", type=int, default=600, help="Per-case seconds before terminating the complete process group (default: 600)")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))
    cases = manifest["cases"]
    if args.cases:
        chosen = {item.strip() for item in args.cases.split(",") if item.strip()}
        unknown = chosen - {case["id"] for case in cases}
        if unknown:
            parser.error("Unknown cases: " + ", ".join(sorted(unknown)))
        cases = [case for case in cases if case["id"] in chosen]
    if not cases:
        parser.error("Select at least one case")
    if args.list:
        for case in cases:
            print(f"{case['id']}: {case['manual_review']}")
        return 0
    if args.timeout < 1 or args.timeout > 600:
        parser.error("--timeout must be between 1 and 600 seconds")
    if not (ROOT / ".venv" / "bin" / "python").exists():
        parser.error("Create the repository .venv and install requirements.txt first")
    codex = shutil.which("codex")
    if not codex:
        parser.error("The Codex CLI must be installed and signed in before running evaluations")
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ("-baseline" if args.baseline else "-skills")
    run_dir = ROOT / ".test-runs" / label
    run_dir.mkdir(parents=True)
    snapshot = run_dir / "source-snapshot"
    copy_source(ROOT, snapshot)
    hashes = source_hashes(snapshot)
    evaluator_hashes = {str(p.relative_to(ROOT)): digest(p) for p in (Path(__file__), ROOT / "evals" / "cases.json")}
    version = subprocess.run([codex, "--version"], text=True, capture_output=True, check=True).stdout.strip()
    started = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_case, case, snapshot, run_dir, manifest["synthetic_now"], args.baseline, codex, args.timeout): case for case in cases}
        for future in as_completed(futures):
            case = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"id": case["id"], "automated_pass": False, "runner_error": f"{type(exc).__name__}: {exc}",
                          "manual_review": {"status": "not_reviewed", "rubric": case["manual_review"]}}
                write_json(run_dir / case["id"] / "result.json", result)
            results.append(result)
            failed = [c["name"] for c in result.get("checks", []) if not c["passed"]]
            print(f"{result['id']}: {'PASS' if result['automated_pass'] else 'FAIL'}" + (" (" + ", ".join(failed) + ")" if failed else ""), flush=True)
    order = {case["id"]: index for index, case in enumerate(cases)}
    results.sort(key=lambda r: order[r["id"]])
    report = {"schema": 1, "created_at": datetime.now(timezone.utc).isoformat(), "synthetic": True,
              "baseline": args.baseline, "baseline_scope": "Same gateway and data; project AGENTS, Skills and coaching docs removed. Not a no-harness baseline.",
              "codex_version": version, "model_selection": "CLI default with user configuration omitted; no model override", "synthetic_now": manifest["synthetic_now"],
              "runtime_seconds": round(time.monotonic() - started, 3), "source_hashes": hashes, "evaluator_hashes": evaluator_hashes,
              "source_still_matches_working_tree": hashes == source_hashes(ROOT),
              "automated_passed": sum(r["automated_pass"] for r in results), "total": len(results),
              "manual_review_status": "not_reviewed", "coverage_limit": "State and boundary checks do not certify French explanation quality, all input variants, month-long learning outcomes, or host-independent isolation.",
              "run_directory": str(run_dir), "results": results}
    output = args.output.resolve() if args.output else run_dir / "report.json"
    write_json(output, report)
    print(f"Report: {output}\nAutomated: {report['automated_passed']}/{len(results)}; manual French/response review is still required.", flush=True)
    return 0 if all(r["automated_pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

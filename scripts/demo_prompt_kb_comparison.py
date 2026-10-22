#!/usr/bin/env python3
"""Compare transcript-only coaching with this harness using seven real Codex calls.

All learners and records are synthetic. This is a small demonstration of state
continuity and enforced evidence, not a benchmark of language-model intelligence.
Raw traces and learner-state snapshots remain under the ignored .test-runs path.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from run_codex_evals import copy_source, digest, parse_trace, probe, source_hashes, write_json

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-10-22T06:00:00+00:00"
WRONG = "Le maison est petite."
CORRECTION = "La maison est petite."
RESUME = "Resume my vocabulary practice. What happened on my last item, and where should I continue?"

POLICY = """You are a French recall coach. Ask one question at a time. Explain briefly
in English, with French where useful. Evaluate the actual answer fairly, accepting
valid paraphrases. A spelling or agreement error is not a judgement about the learner.
For an error, explain the relevant point and invite a correction. Do not fabricate
an answer or a retry. When the learner supplies a correction and asks to continue,
acknowledge it and ask the next curriculum question.

Evidence policy: Preserve the first answer and its original judgement separately
from a correction given after feedback. A coached correction is assisted; it does
not turn the first attempt into independent success and must not create another
scheduled review. A first, incorrect attempt receives one Again scheduling event;
a correct, unassisted first attempt receives Good. Do not invent a review date.
Independent delayed recall requires an unassisted attempt at least one day after
an earlier scheduled attempt. An immediate correction is not delayed recall.
Session progress is not programme mastery. State only what the available evidence
supports; if no previous learner record is available, say so and request the
missing context. Do not infer learner history from static curriculum examples.
"""


def common_context(cards):
    return (
        "This is a synthetic demonstration. No actual learner is being assessed.\n\n"
        + POLICY
        + "\nStatic knowledge base (reference material, NOT learner history):\n"
        + json.dumps(cards, ensure_ascii=False, indent=2)
        + "\nTeaching example, NOT a past learner record: In 'Le maison est petite.', "
        "the error is 'Le': maison is feminine, so use 'La'. 'Petite' is already correct.\n"
    )


def seed(workspace):
    code = """import json
from datetime import datetime
from coach.engine import Coach
c = Coach('state', datetime.fromisoformat(%r))
c.init()
print(json.dumps(c.start('vocab', 3), ensure_ascii=False))
""" % NOW
    result = subprocess.run([str(workspace / ".venv/bin/python"), "-c", code], cwd=workspace,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def build_prompt(arm, common, learner, transcript=None, first_packet=None):
    prompt = common
    if arm == "prompt_kb":
        prompt += (
            "\nMode: prompt plus static knowledge base only. Answer using ONLY the "
            "material in this prompt. Do not use any tool, inspect any file, run any "
            "command, browse, or write anything. You have no durable learner database. "
            "You may keep track within the conversation transcript supplied below, "
            "but do not claim to have saved anything outside it.\n"
        )
    else:
        prompt += (
            "\nMode: the French Recall Coach harness in this project. Use its Skills "
            "and public gateway for practice and evidence. The gateway is "
            ".venv/bin/python -m coach. Use the existing state directory 'state'. "
            f"For this synthetic demonstration only, put --now {NOW} before each "
            "gateway subcommand. Do not use external services or modify the harness.\n"
        )
        if first_packet:
            prompt += "Current question checkpoint: " + json.dumps({
                "session_id": first_packet["session_id"],
                "item_id": first_packet["item_id"],
                "prompt": first_packet["prompt"],
            }, ensure_ascii=False) + "\n"
    if transcript is not None:
        prompt += (
            "\nExact prior conversation transcript supplied by the demonstration "
            "runner (synthetic):\n" + json.dumps(transcript, ensure_ascii=False, indent=2) + "\n"
        )
    else:
        prompt += "\nNo prior conversation transcript is supplied in this request.\n"
    return prompt + "\nCurrent learner request:\n" + learner


def tool_events(path):
    """Record all completed non-text/non-reasoning items, not just shell calls."""
    events, types = [], []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item", {})
        kind = item.get("type", "unknown")
        types.append(kind)
        if kind not in ("agent_message", "reasoning"):
            events.append({"type": kind, "id": item.get("id")})
    return events, sorted(set(types))


def run_call(name, arm, workspace, prompt, directory, codex, timeout):
    directory.mkdir()
    (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
    before = probe(workspace) if arm == "harness" else None
    if before:
        write_json(directory / "before.json", before)
    hashes_before = source_hashes(workspace) if arm == "harness" else None
    command = [codex, "exec", "--ephemeral", "--ignore-user-config", "--sandbox",
               "workspace-write" if arm == "harness" else "read-only", "--json",
               "-C", str(workspace), "-o", str(directory / "final.txt"), prompt]
    started, timed_out = time.monotonic(), False
    with (directory / "trace.jsonl").open("w", encoding="utf-8") as stdout, \
            (directory / "stderr.txt").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=workspace, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                code = process.wait()
    elapsed = round(time.monotonic() - started, 3)
    usage, commands, complete, errors = parse_trace(directory / "trace.jsonl")
    observed_tools, item_types = tool_events(directory / "trace.jsonl")
    final_file = directory / "final.txt"
    final = final_file.read_text(encoding="utf-8") if final_file.exists() else ""
    after = probe(workspace) if arm == "harness" else None
    if after:
        write_json(directory / "after.json", after)
    checks = [{"name": "real_codex_turn_completed", "passed": code == 0 and complete and bool(final.strip()) and not timed_out},
              {"name": "trace_parsed_without_error", "passed": errors == 0}]
    if arm == "prompt_kb":
        checks += [{"name": "zero_observed_tool_calls", "passed": not observed_tools},
                   {"name": "no_workspace_files_created", "passed": not any(p.name != ".git" for p in workspace.iterdir())}]
    else:
        checks += [{"name": "harness_source_unchanged", "passed": hashes_before == source_hashes(workspace)},
                   {"name": "actual_gateway_used", "passed": any("-m coach" in c["command"] and c["exit_code"] == 0 for c in commands)}]
    public = {"id": name, "arm": arm, "final_response": final.replace(str(workspace), "<workspace>"),
              "runtime_seconds": elapsed, "usage": usage, "returncode": code, "timed_out": timed_out,
              "observed_tool_calls": len(observed_tools), "observed_item_types": item_types,
              "gateway_command_count": sum("-m coach" in c["command"] for c in commands),
              "prompt_sha256": digest(directory / "prompt.txt"), "checks": checks,
              "manual_review": "pending", "raw_artifact_directory": directory.name}
    write_json(directory / "result.json", public)
    print(f"{name}: completed={checks[0]['passed']}, tools={len(observed_tools)}, {elapsed}s", flush=True)
    return {"public": public, "before": before, "after": after, "commands": commands}


def state_checks(first, second, resumed):
    t1, t2, t3 = (r["after"]["tables"] for r in (first, second, resumed))
    attempt1 = t1["attempts"][0] if len(t1["attempts"]) == 1 else {}
    attempt2 = t2["attempts"][0] if len(t2["attempts"]) == 1 else {}
    retry = json.loads(attempt2.get("retries", "[]"))
    sessions = t2["sessions"]
    checks = [
        ("wrong_answer_was_saved_by_the_actual_model_call", attempt1.get("first_answer") == WRONG and attempt1.get("verdict") == "incorrect"),
        ("first_wrong_answer_created_exactly_one_review", len(t1["cards"]) == 1 and len(t1["attempts"]) == 1 and sum(e["kind"] == "attempt_assessed" for e in t1["events"]) == 1),
        ("correction_did_not_overwrite_first_attempt", attempt2.get("first_answer") == WRONG and attempt2.get("verdict") == "incorrect"),
        ("actual_correction_saved_separately_as_assisted", len(retry) == 1 and retry[0].get("answer") == CORRECTION and retry[0].get("assisted") is True),
        ("correction_did_not_create_a_second_review", t2["cards"] == t1["cards"] and sum(e["kind"] == "attempt_assessed" for e in t2["events"]) == 1),
        ("session_continued_to_apartment_question", len(sessions) == 1 and sessions[0]["cursor"] == 1 and json.loads(sessions[0]["queue"])[1] == "v002"),
        ("fresh_process_preserved_original_attempt_and_schedule", t3["attempts"] == t2["attempts"] and t3["cards"] == t2["cards"]),
        ("fresh_process_preserved_checkpoint", t3["sessions"] == t2["sessions"]),
        ("fresh_process_read_the_checkpoint", any("-m coach" in c["command"] and '"v002"' in c["output"] and c["exit_code"] == 0 for c in resumed["commands"])),
    ]
    return [{"name": name, "passed": passed} for name, passed in checks]


def boundary_probe(workspace, item_id):
    """Explicit test injection through the public API, never a claimed model error."""
    before = probe(workspace)
    code = """import json
from datetime import datetime
from coach.engine import Coach
c = Coach('state', datetime.fromisoformat(%r))
result = {}
try:
    result['overwrite_result'] = c.answer(%r, %r)
except Exception as exc:
    result['overwrite_error'] = {'type': type(exc).__name__, 'text': str(exc), 'code': getattr(exc, 'code', None)}
result['duplicate_original_result'] = c.answer(%r, %r)
print(json.dumps(result, ensure_ascii=False))
""" % (NOW, item_id, CORRECTION, item_id, WRONG)
    raw = subprocess.run([str(workspace / ".venv/bin/python"), "-c", code], cwd=workspace,
                         text=True, capture_output=True, check=True)
    observed = json.loads(raw.stdout)
    after = probe(workspace)
    a, b = before["tables"], after["tables"]
    checks = [
        {"name": "overwrite_rejected_as_immutable", "passed": observed.get("overwrite_error", {}).get("code") == "immutable_answer"},
        {"name": "identical_original_replay_is_idempotent", "passed": observed["duplicate_original_result"].get("status") == "already_saved"},
        {"name": "attempts_unchanged_after_both_probes", "passed": a["attempts"] == b["attempts"]},
        {"name": "scheduled_cards_unchanged_after_both_probes", "passed": a["cards"] == b["cards"]},
    ]
    return {"kind": "deterministic public-gateway boundary probe, not a model-generated mistake",
            "attempted_overwrite": CORRECTION, "duplicate_original": WRONG, "observed": observed, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--prepare-only", action="store_true", help="Verify workspaces and unanswered fixture without model calls")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    codex = shutil.which("codex")
    if not codex or not (ROOT / ".venv/bin/python").exists():
        parser.error("Codex and the repository .venv are required")
    started = time.monotonic()
    run_dir = ROOT / ".test-runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-prompt-kb-demo")
    run_dir.mkdir(parents=True)
    harness, baseline = run_dir / "harness-workspace", run_dir / "prompt-kb-workspace"
    copy_source(ROOT, harness)
    (harness / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    (harness / ".gitignore").write_text(".venv/\nstate/\n__pycache__/\n", encoding="utf-8")
    baseline.mkdir()
    for workspace in (harness, baseline):
        subprocess.run(["git", "init", "-q", str(workspace)], check=True, capture_output=True)
    packet = seed(harness)
    fixture = probe(harness)
    assert not fixture["tables"]["attempts"] and not fixture["tables"]["cards"], "Fixture must contain no seeded answers"
    assert packet["prompt"] == "Translate into French: The house is small."
    initial_source_hashes = source_hashes(harness)
    version = subprocess.run([codex, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    cards = json.loads((ROOT / "data/vocab.json").read_text(encoding="utf-8"))[:3]
    common = common_context(cards)
    if args.prepare_only:
        print(f"Fixture verified: unanswered v001; no attempts or scheduled cards.\nRun: {run_dir}")
        return 0
    results = []
    transcripts = {arm: [{"role": "assistant", "content": packet["prompt"]}] for arm in ("prompt_kb", "harness")}
    workspace_for = {"prompt_kb": baseline, "harness": harness}
    first, second, resumed = {}, {}, {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for scene, output, request in (
            ("scene1_first", first, WRONG),
            ("scene1_correction", second, CORRECTION + "\nPlease record my correction and continue to the next question."),
            ("scene2_fresh_resume", resumed, RESUME),
        ):
            futures = {}
            for arm in ("prompt_kb", "harness"):
                transcript = transcripts[arm] if scene.startswith("scene1") else None
                prompt = build_prompt(arm, common, request, transcript, packet if scene == "scene1_first" else None)
                name = scene + "_" + arm
                futures[arm] = pool.submit(run_call, name, arm, workspace_for[arm], prompt,
                                           run_dir / name, codex, args.timeout)
            for arm, future in futures.items():
                result = future.result()
                output[arm] = result
                results.append(result["public"])
                if scene.startswith("scene1"):
                    transcripts[arm].extend([{"role": "user", "content": request},
                                             {"role": "assistant", "content": result["public"]["final_response"]}])
    name = "scene3_manual_handover_prompt_kb"
    prompt = build_prompt("prompt_kb", common, RESUME, transcripts["prompt_kb"])
    handover = run_call(name, "prompt_kb", baseline, prompt, run_dir / name, codex, args.timeout)
    results.append(handover["public"])
    boundary = boundary_probe(harness, packet["item_id"])
    checks = state_checks(first["harness"], second["harness"], resumed["harness"])
    write_json(run_dir / "transcripts.json", transcripts)
    report = {
        "schema": 1, "created_at": datetime.now(timezone.utc).isoformat(), "synthetic": True,
        "real_model_calls": 7, "codex_version": version,
        "model_selection": "Same Codex binary and CLI default, --ignore-user-config, no model override. Exact backend model identity is not emitted by the JSON trace and was not pinned; no guarantee of an immutable model revision.",
        "common_cli_flags": ["exec", "--ephemeral", "--ignore-user-config", "--json"],
        "arm_difference": "Harness: project instructions, executable gateway and durable state, workspace-write sandbox. Prompt+KB: same relevant static content and coaching policies inline, read-only sandbox, explicitly no tools or persistent state.",
        "conversation_method": "Every call is a fresh Codex process. Scene 1 replays each arm's own exact transcript between turns, not a persistent CLI session. Scene 2 deliberately omits that transcript. Scene 3 restores the exact prompt+KB transcript manually.",
        "baseline_boundary": "No engine or learner-state context provided. Zero-tool compliance is checked in the trace. This is not a claim of OS-level isolation or a comparison against a chat product with its own saved history.",
        "synthetic_now": NOW, "initial_fixture": "Public API init + start(vocab, 3), no answers seeded",
        "static_knowledge_base": cards, "common_coaching_policy": POLICY,
        "source_hashes": initial_source_hashes, "runner_sha256": digest(Path(__file__)),
        "source_matches_current_tree": initial_source_hashes == source_hashes(ROOT),
        "runtime_seconds": round(time.monotonic() - started, 3),
        "results": results, "harness_state_checks": checks, "gateway_boundary_probe": boundary,
        "manual_review_status": "pending",
        "limits": ["One synthetic learner trace, not a statistical benchmark.",
                   "French teaching quality and honesty require manual reading of the actual responses.",
                   "A prompt+KB with the whole prior transcript can recover conversation context; the cold-resume comparison measures the benefit of explicit persistent state.",
                   "The boundary probe intentionally submits invalid/repeated operations; it does not claim the baseline model made these mistakes.",
                   "No measured claim of better long-term retention, lower cost, faster replies or universal model superiority."],
    }
    all_checks = checks + boundary["checks"] + [c for r in results for c in r["checks"]]
    report["automated_checks_passed"] = sum(c["passed"] for c in all_checks)
    report["automated_checks_total"] = len(all_checks)
    report["automated_pass"] = all(c["passed"] for c in all_checks)
    write_json(run_dir / "public-report.json", report)
    print(f"Report: {run_dir / 'public-report.json'}\nChecks: {report['automated_checks_passed']}/{len(all_checks)}", flush=True)
    return 0 if report["automated_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""JSON CLI: a small, inspectable tool surface for Codex and terminal learners."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sqlite3
import sys


def parser():
    p = argparse.ArgumentParser(description="French Recall Coach local learning gateway")
    p.add_argument("--state-dir", default="state", help="Separate learner profile directory (default: state)")
    p.add_argument("--now", help="ISO8601 with timezone, for synthetic tests only; omit for real learners")
    s = p.add_subparsers(dest="command", required=True)
    s.add_parser("init", help="Create a learner profile without overwriting existing progress")
    s.add_parser("doctor", help="Check runtime, curriculum and optional state")
    start = s.add_parser("start", help="Start or resume a bounded session")
    start.add_argument("--module", choices=["vocab", "conjugation", "numbers"], default="vocab")
    start.add_argument("--limit", type=int, default=30)
    for command in ("next", "stop"):
        q = s.add_parser(command)
        q.add_argument("--session", required=True)
    for command in ("answer", "retry"):
        q = s.add_parser(command)
        q.add_argument("--item", required=True)
        source = q.add_mutually_exclusive_group(required=True)
        source.add_argument("--text", help="Actual learner answer; shell-quote it or use --text-file")
        # An optional file path avoids shell interpolation of untrusted learner text.
        source.add_argument("--text-file", help="Read the actual UTF-8 answer from a file without shell interpolation")
        source.add_argument("--text-json", help='Read a UTF-8 JSON object {"answer":"..."}; preserves exact string boundaries')
    for command in ("hint", "advance"):
        q = s.add_parser(command)
        q.add_argument("--item", required=True)
    assess = s.add_parser("assess")
    assess.add_argument("--item", required=True)
    assess.add_argument("--verdict", required=True, choices=["correct", "incorrect", "uncertain"])
    assess.add_argument("--reason", required=True)
    skip = s.add_parser("skip")
    skip.add_argument("--item", required=True)
    skip.add_argument("--reason", required=True)
    for command in ("status", "report", "export"):
        s.add_parser(command)
    evaluate = s.add_parser("evaluate", help="Outer loop: calculate a plan proposal after seven days")
    evaluate.add_argument("--module", choices=["vocab", "conjugation", "numbers"], required=True)
    apply = s.add_parser("apply", help="Outer loop only: apply a checked evaluation exactly once")
    apply.add_argument("--evaluation", required=True)
    pref = s.add_parser("preference")
    pref.add_argument("--scope", choices=["all", "vocab", "conjugation", "numbers"], required=True)
    pref.add_argument("--value", required=True)
    pref.add_argument("--reason", required=True, help="Record the learner request or other source")
    pref.add_argument("--supersedes", type=int)
    return p


def compact(value):
    """Keep tool packets bounded; the full record remains in the private export."""
    if isinstance(value, dict):
        return {key: ({"count": len(v), "first_five": v[:5]} if key == "missing" else compact(v)) for key, v in value.items()}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        from .content import MODULES, curriculum, fingerprint
        from .engine import Coach, CoachError
        coach = Coach(args.state_dir, args.now)
        c = args.command
        if c == "doctor":
            versions = {name: importlib.metadata.version(name) for name in ("fsrs", "typing_extensions")}
            if versions != {"fsrs": "6.3.2", "typing_extensions": "4.15.0"}:
                raise CoachError("environment_drift", "Dependency versions differ. Reinstall requirements.txt in the project virtual environment.")
            if coach.db.exists():
                with coach.transaction():
                    pass
            result = {"status": "ok", "python": sys.version.split()[0], "dependencies": versions,
                      "curriculum": {m: len(curriculum(m)) for m in MODULES}, "content_hash": fingerprint(),
                      "state": "checked" if coach.db.exists() else "not_initialised"}
        elif c == "init":
            result = coach.init()
        elif c == "start":
            result = coach.start(args.module, args.limit)
        elif c == "next":
            result = coach.next(args.session)
        elif c == "stop":
            result = coach.stop(args.session)
        elif c in ("answer", "retry"):
            from pathlib import Path
            if args.text_json:
                payload = json.loads(Path(args.text_json).read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or set(payload) != {"answer"} or not isinstance(payload["answer"], str):
                    raise ValueError('Answer JSON must contain exactly one string field: "answer".')
                text = payload["answer"]
            else:
                text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
            result = getattr(coach, c)(args.item, text)
        elif c == "hint":
            result = coach.hint(args.item)
        elif c == "advance":
            result = coach.advance(args.item)
        elif c == "assess":
            result = coach.assess(args.item, args.verdict, args.reason)
        elif c == "skip":
            result = coach.skip(args.item, args.reason)
        elif c == "evaluate":
            result = coach.evaluate(args.module)
        elif c == "apply":
            result = coach.apply(args.evaluation)
        elif c == "preference":
            result = coach.preference(args.scope, args.value, args.reason, args.supersedes)
        elif c == "export":
            result = coach.export()
        else:
            result = coach.status()
            if c == "report":
                result["report_scope"] = "Local learning summary only. Nothing was sent or shared."
        print(json.dumps(result if c == "export" else compact(result), ensure_ascii=False, indent=2))
        return 0
    except ImportError as exc:
        print(json.dumps({"error": "missing_dependency", "severity": "blocking", "message": f"{exc}. Activate the project environment and install requirements.txt.", "saved": False}), file=sys.stderr)
        return 2
    except Exception as exc:
        # Preserve state and expose actionable failures, without a success-shaped result.
        if isinstance(exc, (OSError, sqlite3.DatabaseError, ValueError)) or exc.__class__.__name__ == "CoachError":
            print(json.dumps({"error": getattr(exc, "code", "state_or_input_error"), "severity": "blocking", "message": str(exc), "saved": False}, ensure_ascii=False), file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())

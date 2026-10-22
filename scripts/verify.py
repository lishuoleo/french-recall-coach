"""Run the reproducible local verification gate without model/API calls."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_hash():
    files = sorted(p for folder in ("coach", "data", "tests", "scripts", ".agents")
                   for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".json", ".md", ".yaml"))
    files += [ROOT / "AGENTS.md", ROOT / "requirements.txt"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "files": hashes}


def main():
    commands = [[sys.executable, "-m", "coach", "doctor"],
                [sys.executable, "scripts/validate_harness.py"],
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                [sys.executable, "scripts/demo.py"]]
    runs = []
    for command in commands:
        start = time.monotonic()
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        runs.append({"command": ["python", *command[1:]], "returncode": proc.returncode,
                     "elapsed_seconds": round(time.monotonic() - start, 3), "stdout": proc.stdout, "stderr": proc.stderr})
        print(f"{'PASS' if proc.returncode == 0 else 'FAIL'} {' '.join(command[1:])}", flush=True)
        if proc.returncode:
            print(proc.stdout + proc.stderr)
    output = ROOT / ".test-runs/verification.json"
    output.parent.mkdir(exist_ok=True)
    result = {"at": datetime.now(timezone.utc).isoformat(), "python": sys.version.split()[0],
              "passed": all(r["returncode"] == 0 for r in runs), "source": source_hash(), "runs": runs,
              "scope": "Deterministic and synthetic programme verification only; real Codex evaluations run separately."}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Evidence: .test-runs/verification.json")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

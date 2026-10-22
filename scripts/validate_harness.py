"""Bounded structural checks; behavioural correctness is tested separately."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def validate(root=ROOT):
    errors = []
    names = set()
    for path in sorted((root / ".agents/skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3 or parts[0].strip():
            errors.append(f"{path.relative_to(root)}: missing YAML frontmatter")
            continue
        fields = dict(re.findall(r"^(name|description):\s*(.+)$", parts[1], re.M))
        name = fields.get("name", "")
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name) or name in names or name != path.parent.name:
            errors.append(f"{path.relative_to(root)}: invalid/duplicate skill name")
        names.add(name)
        if not fields.get("description", "").strip():
            errors.append(f"{path.relative_to(root)}: missing discovery description")
    if names != {"french-vocab", "french-conjugation", "french-numbers"}:
        errors.append("Expected the three scoped practice Skills")
    markdown = [root / "README.md", root / "AGENTS.md", *sorted((root / "docs").glob("*.md")),
                *sorted((root / ".agents/skills").glob("*/SKILL.md")), *sorted((root / "evals").glob("*.md"))]
    for path in markdown:
        if not path.exists():
            errors.append(f"Missing {path.relative_to(root)}")
            continue
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = target.strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / unquote(target)).exists():
                errors.append(f"{path.relative_to(root)}: broken link {target}")
    for path in (root / "coach").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "fsrs" and path.name != "scheduler.py":
                errors.append(f"{path.name}: FSRS belongs in the shared adapter")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "sqlite3" and node.func.attr == "connect" and path.name != "engine.py":
                    errors.append(f"{path.name}: state connection belongs in the gateway")
    inventory = root / "docs/rule-inventory.md"
    if inventory.exists():
        rule_ids = re.findall(r"^\|\s*(R\d{3})\s*\|", inventory.read_text(encoding="utf-8"), re.M)
        if not rule_ids or len(rule_ids) != len(set(rule_ids)):
            errors.append("Rule inventory needs unique stable IDs")
    for name in ("state/", ".test-runs/", ".venv/"):
        if name not in (root / ".gitignore").read_text(encoding="utf-8").splitlines():
            errors.append(f"Private/generated directory is not ignored: {name}")
    return {"status": "failed" if errors else "passed", "errors": errors, "skills": sorted(names),
            "scope": "Frontmatter, local links, rule IDs, private-path exclusions and limited AST ownership checks. This does not prove semantic instruction consistency or model behaviour."}


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["errors"]))

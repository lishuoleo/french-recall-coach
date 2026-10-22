"""Replay the workshop example against real tools, with synthetic learner data."""
from pathlib import Path
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coach.engine import Coach


def main():
    root = Path(__file__).resolve().parents[1]
    scratch = root / ".test-runs"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="demo-", dir=scratch) as profile:
        coach = Coach(profile, "2026-01-01T09:00:00Z")
        coach.init()
        question = coach.start("vocab", 1)
        item = question["item_id"]
        print("Synthetic workshop demonstration. No real learner or model claims.\n")
        print("Question:", question["prompt"])
        first = coach.answer(item, "Le maison est petite.")
        print("First answer saved:", first["first_answer"], "|", first["phase"])
        feedback = coach.assess(item, "incorrect", "Maison is feminine: use la. Petite already agrees correctly.")
        print("Feedback:", feedback["reason"])
        resumed = Coach(profile, "2026-01-01T09:01:00Z")
        print("Fresh process checkpoint:", resumed.next(question["session_id"])["phase"])
        correction = resumed.retry(item, "La maison est petite.")
        print("Correction:", json.dumps(correction, ensure_ascii=False))
        print("Session:", resumed.advance(item)["phase"])
        print("Programme complete:", resumed.status()["programme_complete"])
        export = resumed.export()
        attempt = export["tables"]["attempts"][0]
        print("Saved first verdict:", attempt["verdict"])
        print("FSRS review entries:", sum(a["review_log"] is not None for a in export["tables"]["attempts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

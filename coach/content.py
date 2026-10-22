"""Read only the active curriculum. French examples are data, never instructions."""
from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("vocab", "conjugation", "numbers")


def normalise(text: str) -> str:
    """Accept case, typography and 1990 hyphenation, but preserve French accents."""
    text = unicodedata.normalize("NFC", text).casefold().strip()
    text = text.replace("’", "'").replace("‑", "-").replace("–", "-")
    text = re.sub(r"[-\s]+", " ", text)
    return text.rstrip(".!? ")


def cardinal(n: int) -> str:
    if type(n) is not int or not 0 <= n <= 999:
        raise ValueError("Cardinal range is 0–999")
    small = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept",
             "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze",
             "quinze", "seize"]
    if n < 17:
        return small[n]
    if n < 20:
        return "dix-" + small[n - 10]
    if n < 70:
        tens = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
        a, b = divmod(n, 10)
        return tens[a] + (" et un" if b == 1 else "-" + small[b] if b else "")
    if n < 80:
        return "soixante" + (" et " if n == 71 else "-") + cardinal(n - 60)
    if n < 100:
        return "quatre-vingts" if n == 80 else "quatre-vingt-" + cardinal(n - 80)
    a, b = divmod(n, 100)
    prefix = "cent" if a == 1 else small[a] + " cent"
    return prefix + (" " + cardinal(b) if b else "s" if a > 1 else "")


def ordinal(n: int) -> str:
    if not 1 <= n <= 99:
        raise ValueError("Ordinal range is 1–99")
    if n == 1:
        return "premier"
    value = cardinal(n)
    if value.endswith("cinq"):
        value += "u"
    elif value.endswith("neuf"):
        value = value[:-1] + "v"
    elif value.endswith("e"):
        value = value[:-1]
    elif value.endswith("vingts"):
        value = value[:-1]
    return value + "ième"


MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre"]


def number_cards() -> list[dict]:
    """Persistable assessment universe: 20 generated tasks per stage, seed 42."""
    rng = random.Random(42)
    cards = []
    ranges = [(0, 20), (21, 69), (70, 99), (100, 999)]
    for stage, (lo, hi) in enumerate(ranges, 1):
        count = 20 if stage == 1 else 10
        values = [lo, hi] + rng.sample(range(lo + 1, hi), count - 2)
        for value in values:
            cards.append({"id": f"n{stage}-c{value}", "week": stage,
                          "prompt": f"Write {value} in French words (metropolitan French).",
                          "answers": [cardinal(value)], "target": str(value),
                          "explanation": "Use the metropolitan French cardinal form.",
                          "tags": ["cardinal"], "value": value})
        if stage == 2:
            for value in [1, 2, 3, 4, 5, 9, 11, 20, 21, 80]:
                answers = [ordinal(value)]
                if value == 2:
                    answers.append("second")
                cards.append({"id": f"n2-o{value}", "week": 2,
                              "prompt": f"Write the masculine ordinal for position {value} in French.",
                              "answers": answers, "target": str(value),
                              "explanation": "Use the masculine ordinal; premier is irregular.",
                              "tags": ["ordinal"]})
        if stage == 3:
            for index, (day, month) in enumerate([(1, 1), (14, 7), (25, 12), (2, 2), (8, 3),
                                                 (30, 4), (15, 5), (21, 6), (31, 8), (11, 11)]):
                phrase = ("premier" if day == 1 else cardinal(day)) + " " + MONTHS[month - 1]
                cards.append({"id": f"n3-d{index}", "week": 3,
                              "prompt": f"Write the date {day} {MONTHS[month - 1]} in French words, including le.",
                              "answers": ["le " + phrase], "target": phrase,
                              "explanation": "Dates use cardinal numbers, except le premier for the first.",
                              "tags": ["date"]})
        if stage == 4:
            for hour, minute in [(0, 0), (1, 0), (8, 15), (9, 30), (10, 45), (12, 0),
                                  (13, 10), (17, 20), (21, 5), (23, 59)]:
                hour_words = "une" if hour == 1 else "vingt et une" if hour == 21 else cardinal(hour)
                phrase = hour_words + (" heure" if hour in (0, 1) else " heures")
                if minute:
                    phrase += " " + cardinal(minute)
                answers = [phrase]
                if hour == 0 and minute == 0:
                    answers.append("minuit")
                if hour == 12 and minute == 0:
                    answers.append("midi")
                cards.append({"id": f"n4-t{hour:02}{minute:02}", "week": 4,
                              "prompt": f"Write {hour:02}:{minute:02} in French words using the 24-hour clock: hour + heure(s) + minute number. Omit il est and the word minutes.",
                              "answers": answers, "target": f"{hour:02}:{minute:02}",
                              "explanation": "Use the 24-hour hour followed by minutes; heure agrees with the hour.",
                              "tags": ["time"]})
    return cards


def curriculum(module: str) -> list[dict]:
    if module not in MODULES:
        raise ValueError(f"Choose a module from {', '.join(MODULES)}")
    if module == "numbers":
        cards = number_cards()
    else:
        name = "vocab.json" if module == "vocab" else "verbs.json"
        cards = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
    seen = set()
    for card in cards:
        if not isinstance(card, dict) or not all(k in card for k in ("id", "week", "prompt", "answers", "explanation")):
            raise ValueError("Malformed curriculum card")
        if card["id"] in seen or type(card["week"]) is not int or card["week"] not in range(1, 5):
            raise ValueError("Duplicate card ID or invalid stage")
        if not isinstance(card["answers"], list) or not card["answers"] or any(not isinstance(a, str) or not a.strip() for a in card["answers"]):
            raise ValueError("Every card needs non-empty reference answers")
        seen.add(card["id"])
    return cards


def fingerprint() -> str:
    data = {module: curriculum(module) for module in MODULES}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

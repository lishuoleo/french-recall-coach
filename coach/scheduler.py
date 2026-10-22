"""The single FSRS adapter. No model-generated review dates."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

SCHEDULER = Scheduler(desired_retention=0.9, enable_fuzzing=False)


def utc(value: str | datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Time must include a timezone")
    return value.astimezone(timezone.utc)


def review(module: str, card_id: str, saved: dict | None, correct: bool,
           assisted: bool, now: datetime) -> tuple[dict, dict]:
    key = int(hashlib.sha256(f"{module}:{card_id}".encode()).hexdigest()[:13], 16)
    card = Card.from_dict(saved) if saved else Card(card_id=key, due=now)
    if card.last_review is not None and now < card.last_review:
        raise ValueError("Review time cannot precede the last review")
    rating = Rating.Good if correct and not assisted else Rating.Again
    updated, log = SCHEDULER.review_card(card, rating, review_datetime=now)
    return updated.to_dict(), log.to_dict()

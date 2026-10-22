"""Validated, transactional gateway for learning state and outer-loop decisions."""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from .content import MODULES, curriculum, fingerprint, normalise
from .scheduler import review, utc

SCHEMA = 2
BASE_NEW = {"vocab": 10, "conjugation": 6, "numbers": 5}
MAX_ITEMS = 30
MAX_RETRIES = 2


class CoachError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise CoachError(code, message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Coach:
    def __init__(self, state_dir: str | Path = "state", now=None):
        self.state_dir = Path(state_dir)
        self.db = self.state_dir / "coach.sqlite3"
        self.now = utc(now)
        self.catalogue = {m: {c["id"]: c for c in curriculum(m)} for m in MODULES}
        self.content_hash = fingerprint()

    @contextmanager
    def transaction(self, initialise=False):
        require(not self.state_dir.is_symlink() and not self.db.is_symlink(), "unsafe_path", "State directory and database must not be symbolic links.")
        require(initialise or self.db.exists(), "not_initialised", "Run init before practising. Existing progress will not be overwritten.")
        if initialise:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            con.execute("BEGIN IMMEDIATE")
            if not initialise:
                self._check(con)
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _check(self, con):
        meta = dict(con.execute("SELECT key,value FROM meta"))
        require(meta.get("schema") == str(SCHEMA), "schema_mismatch", "Unsupported state schema. Preserve this database and use a compatible release.")
        require(meta.get("content_hash") == self.content_hash, "content_drift", "Curriculum changed. Preserve/export the old database with its matching release; use a new state directory for the new curriculum.")
        require(con.execute("PRAGMA quick_check").fetchone()[0] == "ok", "corrupt_state", "Database integrity check failed. Stop and recover a backup.")
        started = meta.get("started")
        require(started is not None and self.now >= utc(started), "clock_reversed", "Current time precedes this learner profile.")
        last_event = con.execute("SELECT at FROM events ORDER BY id DESC LIMIT 1").fetchone()
        require(last_event is None or self.now >= utc(last_event[0]), "clock_reversed", "Current time precedes the latest saved action. Check the clock; progress was not changed.")
        plans = [dict(r) for r in con.execute("SELECT * FROM plans")]
        require({p["module"] for p in plans} == set(MODULES), "invalid_state", "A module plan is missing or unknown.")
        for plan in plans:
            require(type(plan["stage"]) is int and 1 <= plan["stage"] <= 5
                    and type(plan["quota"]) is int and 1 <= plan["quota"] <= BASE_NEW[plan["module"]]
                    and plan["review_factor"] in (1.0, 1.5) and type(plan["revision"]) is int and plan["revision"] >= 0
                    and utc(started) <= utc(plan["period_start"]) <= self.now
                    and utc(plan["period_start"]) <= utc(plan["last_evaluated"]) <= self.now,
                    "invalid_state", "Invalid programme plan. Preserve the database and investigate; do not reset it.")
        for card in con.execute("SELECT * FROM cards"):
            require(card["module"] in MODULES and card["card_id"] in self.catalogue[card["module"]], "invalid_state", "Stored card is not in this curriculum.")
            saved = json.loads(card["fsrs"])
            require(isinstance(saved, dict) and saved.get("due") == card["due"] and saved.get("last_review") is not None,
                    "invalid_state", "Stored scheduling fields disagree.")
            require(utc(started) <= utc(saved["last_review"]) <= self.now and utc(card["due"]) >= utc(saved["last_review"]),
                    "invalid_state", "Stored review dates are inconsistent.")

    def _event(self, con, kind, payload):
        con.execute("INSERT INTO events(at,kind,payload) VALUES(?,?,?)", (self.now.isoformat(), kind, encode(payload)))

    def init(self):
        with self.transaction(initialise=True) as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
                self._check(con)
                return {"status": "already_initialised", "schema": SCHEMA, "modules": list(MODULES)}
            require(not con.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone(), "invalid_state", "Unrecognised existing database; it will not be overwritten.")
            statements = [
                "CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
                "CREATE TABLE plans(module TEXT PRIMARY KEY,stage INTEGER NOT NULL,quota INTEGER NOT NULL,review_factor REAL NOT NULL,revision INTEGER NOT NULL,period_start TEXT NOT NULL,last_evaluated TEXT NOT NULL)",
                "CREATE TABLE cards(module TEXT NOT NULL,card_id TEXT NOT NULL,fsrs TEXT NOT NULL,due TEXT NOT NULL,PRIMARY KEY(module,card_id))",
                "CREATE TABLE sessions(id TEXT PRIMARY KEY,module TEXT NOT NULL,queue TEXT NOT NULL,cursor INTEGER NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,FOREIGN KEY(module) REFERENCES plans(module))",
                "CREATE UNIQUE INDEX one_active_session ON sessions(module) WHERE status='active'",
                "CREATE TABLE exposures(item_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,hinted INTEGER NOT NULL,module TEXT NOT NULL,card_id TEXT NOT NULL,at TEXT NOT NULL,FOREIGN KEY(session_id) REFERENCES sessions(id))",
                "CREATE TABLE attempts(item_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,module TEXT NOT NULL,card_id TEXT NOT NULL,first_answer TEXT NOT NULL,assisted INTEGER NOT NULL,verdict TEXT NOT NULL,source TEXT NOT NULL,reason TEXT NOT NULL,at TEXT NOT NULL,is_new INTEGER NOT NULL,delayed INTEGER NOT NULL,review_log TEXT,retries TEXT NOT NULL,FOREIGN KEY(session_id) REFERENCES sessions(id))",
                "CREATE TABLE evaluations(id TEXT PRIMARY KEY,module TEXT NOT NULL,revision INTEGER NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL,applied INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE preferences(id INTEGER PRIMARY KEY,scope TEXT NOT NULL,kind TEXT NOT NULL,value TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,supersedes INTEGER,FOREIGN KEY(supersedes) REFERENCES preferences(id))",
                "CREATE TABLE events(id INTEGER PRIMARY KEY,at TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL)",
            ]
            for sql in statements:
                con.execute(sql)
            con.executemany("INSERT INTO meta VALUES(?,?)", [("schema", str(SCHEMA)), ("content_hash", self.content_hash), ("started", self.now.isoformat())])
            for module in MODULES:
                con.execute("INSERT INTO plans VALUES(?,?,?,?,?,?,?)", (module, 1, BASE_NEW[module], 1.0, 0, self.now.isoformat(), self.now.isoformat()))
            self._event(con, "initialised", {"schema": SCHEMA, "content_hash": self.content_hash})
        return {"status": "initialised", "modules": list(MODULES), "schema": SCHEMA}

    def _plan(self, con, module):
        require(module in MODULES, "invalid_module", "Choose vocab, conjugation or numbers.")
        return dict(con.execute("SELECT * FROM plans WHERE module=?", (module,)).fetchone())

    def _session(self, con, session_id):
        row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        require(row is not None, "unknown_session", "Session does not exist in this learner profile.")
        session = dict(row)
        queue = json.loads(session["queue"])
        require(session["module"] in MODULES and isinstance(queue, list) and 1 <= len(queue) <= MAX_ITEMS
                and all(isinstance(key, str) for key in queue) and len(set(queue)) == len(queue)
                and all(key in self.catalogue[session["module"]] for key in queue)
                and type(session["cursor"]) is int and 0 <= session["cursor"] <= len(queue)
                and session["status"] in ("active", "complete", "stopped")
                and (session["status"] != "active" or session["cursor"] < len(queue))
                and (session["status"] != "complete" or session["cursor"] == len(queue)),
                "invalid_state", "Invalid session checkpoint. Preserve the database for recovery.")
        return session

    def _item(self, con, item_id, allow_resolved=False):
        require(isinstance(item_id, str) and ":" in item_id, "invalid_item", "Use the item_id returned by start or next.")
        session_id, _, position = item_id.rpartition(":")
        session = self._session(con, session_id)
        require(position.isascii() and position.isdecimal() and position == str(int(position)), "invalid_item", "Use the exact canonical item_id returned by the gateway.")
        queue = json.loads(session["queue"])
        require(int(position) < len(queue), "invalid_item", "Item is outside the session.")
        if not allow_resolved:
            require(session["status"] == "active" and int(position) == session["cursor"], "stale_item", "This is not the current item. Read next before acting.")
        return session, self.catalogue[session["module"]][queue[int(position)]]

    def _packet(self, con, session):
        queue = json.loads(session["queue"])
        base = {"session_id": session["id"], "module": session["module"], "session_status": session["status"],
                "completed_items": session["cursor"], "total_items": len(queue)}
        if session["status"] != "active":
            return {**base, "phase": session["status"], "programme_complete": False,
                    "message": "Session ended; programme completion is checked separately in status."}
        item_id = f"{session['id']}:{session['cursor']}"
        card = self.catalogue[session["module"]][queue[session["cursor"]]]
        attempt = con.execute("SELECT * FROM attempts WHERE item_id=?", (item_id,)).fetchone()
        base.update(item_id=item_id, card_id=card["id"], prompt=card["prompt"],
                    preferences=self._preferences(con, session["module"]))
        if attempt is None:
            return {**base, "phase": "awaiting_answer", "assisted": self._assisted(con, session["module"], card["id"], item_id),
                    "instruction": "Ask this question, then wait for the learner. Do not invent an answer."}
        self._expose(con, session, card, item_id)
        phase = "awaiting_assessment" if attempt["verdict"] == "pending" else "needs_clarification" if attempt["verdict"] == "uncertain" else "feedback"
        return {**base, "phase": phase, "first_answer": attempt["first_answer"], "verdict": attempt["verdict"],
                "assisted": bool(attempt["assisted"]), "assessment_source": attempt["source"], "reason": attempt["reason"],
                "reference_answers": card["answers"], "explanation": card["explanation"],
                "retries": json.loads(attempt["retries"]), "scheduled": attempt["review_log"] is not None,
                "saved": True}

    def _assisted(self, con, module, card_id, item_id):
        exposures = con.execute("SELECT * FROM exposures WHERE module=? AND card_id=?", (module, card_id))
        return any((r["item_id"] == item_id and r["hinted"])
                   or self.now - utc(r["at"]) < timedelta(days=1) for r in exposures)

    def _expose(self, con, session, card, item_id, hinted=False):
        previous = con.execute("SELECT at,hinted FROM exposures WHERE item_id=?", (item_id,)).fetchone()
        con.execute("INSERT INTO exposures VALUES(?,?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET at=excluded.at,hinted=MAX(exposures.hinted,excluded.hinted)",
                    (item_id, session["id"], int(hinted), session["module"], card["id"], self.now.isoformat()))
        if previous is None or previous["at"] != self.now.isoformat() or (hinted and not previous["hinted"]):
            self._event(con, "reference_exposed", {"item_id": item_id, "module": session["module"], "card_id": card["id"], "hint": hinted})

    def start(self, module="vocab", limit=30):
        require(type(limit) is int and 1 <= limit <= MAX_ITEMS, "invalid_limit", f"Session limit must be 1–{MAX_ITEMS} items.")
        with self.transaction() as con:
            plan = self._plan(con, module)
            existing = con.execute("SELECT * FROM sessions WHERE module=? AND status='active'", (module,)).fetchone()
            if existing:
                return self._packet(con, self._session(con, existing["id"]))
            saved = {row["card_id"]: dict(row) for row in con.execute("SELECT * FROM cards WHERE module=?", (module,))}
            due = sorted((v for v in saved.values() if utc(v["due"]) <= self.now), key=lambda c: (c["due"], c["card_id"]))
            review_cap = min(MAX_ITEMS, math.ceil(20 * plan["review_factor"]))
            queue = [c["card_id"] for c in due[:min(limit, review_cap)]]
            today = self.now.date().isoformat()
            used = con.execute("SELECT COUNT(*) FROM attempts WHERE module=? AND is_new=1 AND substr(at,1,10)=?", (module, today)).fetchone()[0]
            available = max(0, plan["quota"] - used)
            if len(due) <= len(queue) and plan["stage"] <= 4:
                new = [c["id"] for c in self.catalogue[module].values() if c["week"] <= plan["stage"] and c["id"] not in saved]
                # Skipped/unresolved new attempts still consume today's attention budget.
                attempted = {r[0] for r in con.execute("SELECT card_id FROM attempts WHERE module=? AND substr(at,1,10)=?", (module, today))}
                queue.extend([key for key in new if key not in attempted][:min(available, limit - len(queue))])
            if not queue:
                next_due = min((v["due"] for v in saved.values()), default=None)
                return {"phase": "waiting", "module": module, "reason": "No due cards or available new-item allowance.",
                        "next_due": next_due, "programme_complete": self._status(con)["programme_complete"]}
            session_id = uuid.uuid4().hex[:16]
            con.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", (session_id, module, encode(queue), 0, "active", self.now.isoformat(), self.now.isoformat()))
            self._event(con, "session_started", {"session_id": session_id, "module": module, "items": len(queue)})
            return self._packet(con, self._session(con, session_id))

    def next(self, session_id):
        with self.transaction() as con:
            return self._packet(con, self._session(con, session_id))

    def hint(self, item_id):
        with self.transaction() as con:
            session, card = self._item(con, item_id)
            require(con.execute("SELECT 1 FROM attempts WHERE item_id=?", (item_id,)).fetchone() is None, "already_answered", "Read the saved feedback instead.")
            self._expose(con, session, card, item_id, hinted=True)
            self._event(con, "hint_given", {"item_id": item_id})
            return {"item_id": item_id, "reference_answers": card["answers"], "explanation": card["explanation"], "assisted": True}

    def _schedule(self, con, attempt, verdict, source, reason):
        saved = con.execute("SELECT fsrs FROM cards WHERE module=? AND card_id=?", (attempt["module"], attempt["card_id"])).fetchone()
        state, log = review(attempt["module"], attempt["card_id"], json.loads(saved[0]) if saved else None,
                            verdict == "correct", bool(attempt["assisted"]), utc(attempt["at"]))
        con.execute("INSERT INTO cards VALUES(?,?,?,?) ON CONFLICT(module,card_id) DO UPDATE SET fsrs=excluded.fsrs,due=excluded.due",
                    (attempt["module"], attempt["card_id"], encode(state), state["due"]))
        con.execute("UPDATE attempts SET verdict=?,source=?,reason=?,review_log=? WHERE item_id=?",
                    (verdict, source, reason, encode(log), attempt["item_id"]))
        self._event(con, "attempt_assessed", {"item_id": attempt["item_id"], "verdict": verdict, "source": source, "rating": log["rating"]})

    def answer(self, item_id, text):
        require(isinstance(text, str) and 0 < len(text.strip()) <= 4000, "invalid_answer", "Provide a non-empty answer of at most 4,000 characters.")
        with self.transaction() as con:
            self._item(con, item_id, allow_resolved=True)
            existing = con.execute("SELECT * FROM attempts WHERE item_id=?", (item_id,)).fetchone()
            if existing:
                require(existing["first_answer"] == text, "immutable_answer", "The first answer is already saved. Use retry for a correction; never overwrite it.")
                return {"item_id": item_id, "status": "already_saved", "verdict": existing["verdict"], "saved": True}
            session, card = self._item(con, item_id)
            assisted = self._assisted(con, session["module"], card["id"], item_id)
            saved = con.execute("SELECT fsrs FROM cards WHERE module=? AND card_id=?", (session["module"], card["id"])).fetchone()
            previous = json.loads(saved[0]) if saved else None
            delayed = bool(previous and previous.get("last_review") and self.now - utc(previous["last_review"]) >= timedelta(days=1))
            con.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (item_id, session["id"], session["module"], card["id"], text, int(assisted),
                         "pending", "unassessed", "", self.now.isoformat(), int(saved is None), int(delayed), None, "[]"))
            self._event(con, "first_answer_saved", {"item_id": item_id, "delayed": delayed})
            if normalise(text) in [normalise(a) for a in card["answers"]]:
                attempt = dict(con.execute("SELECT * FROM attempts WHERE item_id=?", (item_id,)).fetchone())
                self._schedule(con, attempt, "correct", "reference_match", "Matches an accepted reference after typographic normalisation.")
            return self._packet(con, session)

    def assess(self, item_id, verdict, reason):
        require(verdict in ("correct", "incorrect", "uncertain"), "invalid_verdict", "Choose correct, incorrect or uncertain.")
        require(isinstance(reason, str) and 3 <= len(reason.strip()) <= 2000, "missing_reason", "Explain the linguistic judgement in 3–2,000 characters.")
        with self.transaction() as con:
            session, card = self._item(con, item_id)
            row = con.execute("SELECT * FROM attempts WHERE item_id=?", (item_id,)).fetchone()
            require(row is not None, "no_answer", "Save the learner's actual first answer before assessing it.")
            attempt = dict(row)
            if attempt["verdict"] not in ("pending", "uncertain"):
                require(attempt["verdict"] == verdict and attempt["reason"] == reason, "already_assessed", "This attempt already has a final assessment.")
                return self._packet(con, session)
            if verdict == "uncertain":
                con.execute("UPDATE attempts SET verdict='uncertain',source='agent_judgement',reason=? WHERE item_id=?", (reason, item_id))
                self._event(con, "assessment_uncertain", {"item_id": item_id, "reason": reason})
            else:
                self._schedule(con, attempt, verdict, "agent_judgement", reason)
            return self._packet(con, session)

    def retry(self, item_id, text):
        require(isinstance(text, str) and 0 < len(text.strip()) <= 4000, "invalid_answer", "Provide a non-empty correction of at most 4,000 characters.")
        with self.transaction() as con:
            session, card = self._item(con, item_id)
            row = con.execute("SELECT * FROM attempts WHERE item_id=?", (item_id,)).fetchone()
            require(row is not None and row["verdict"] in ("correct", "incorrect"), "not_assessed", "Resolve the first attempt before recording a coached correction.")
            retries = json.loads(row["retries"])
            if retries and retries[-1]["answer"] == text:
                return {"status": "already_saved", "item_id": item_id, "retries": retries, "scheduled_again": False}
            require(len(retries) < MAX_RETRIES, "retry_limit", "Two corrections are recorded. Explain briefly and advance, or stop this session.")
            retries.append({"answer": text, "matches_reference": normalise(text) in [normalise(a) for a in card["answers"]],
                            "at": self.now.isoformat(), "assisted": True})
            con.execute("UPDATE attempts SET retries=? WHERE item_id=?", (encode(retries), item_id))
            self._expose(con, session, card, item_id)
            self._event(con, "correction_saved", {"item_id": item_id, "retry_count": len(retries)})
            return {"item_id": item_id, "retries": retries, "first_verdict": row["verdict"], "scheduled_again": False, "saved": True}

    def advance(self, item_id):
        with self.transaction() as con:
            session, card = self._item(con, item_id, allow_resolved=True)
            index = int(item_id.rsplit(":", 1)[1])
            if session["cursor"] > index:
                return self._packet(con, session)
            require(session["status"] == "active" and session["cursor"] == index, "stale_item", "This is not the current item.")
            attempt = con.execute("SELECT verdict FROM attempts WHERE item_id=?", (item_id,)).fetchone()
            require(attempt is not None and attempt["verdict"] in ("correct", "incorrect", "skipped"), "unfinished_item", "Answer and assess this item, or explicitly skip it, before advancing.")
            cursor = session["cursor"] + 1
            status = "complete" if cursor == len(json.loads(session["queue"])) else "active"
            con.execute("UPDATE sessions SET cursor=?,status=?,updated=? WHERE id=?", (cursor, status, self.now.isoformat(), session["id"]))
            self._event(con, "item_advanced", {"item_id": item_id, "session_status": status})
            return self._packet(con, self._session(con, session["id"]))

    def skip(self, item_id, reason):
        require(isinstance(reason, str) and 3 <= len(reason.strip()) <= 2000, "missing_reason", "Give a reason for leaving this item unscored.")
        with self.transaction() as con:
            session, card = self._item(con, item_id)
            attempt = con.execute("SELECT * FROM attempts WHERE item_id=?", (item_id,)).fetchone()
            require(attempt is None or attempt["verdict"] in ("pending", "uncertain", "skipped"), "already_assessed", "A scored attempt cannot be changed to skipped.")
            if attempt is None:
                is_new = con.execute("SELECT 1 FROM cards WHERE module=? AND card_id=?", (session["module"], card["id"])).fetchone() is None
                con.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (item_id, session["id"], session["module"], card["id"], "", 0, "skipped", "learner_skip", reason, self.now.isoformat(), int(is_new), 0, None, "[]"))
            else:
                con.execute("UPDATE attempts SET verdict='skipped',reason=?,source='learner_skip' WHERE item_id=?", (reason, item_id))
            self._event(con, "item_skipped", {"item_id": item_id, "reason": reason})
            return self._packet(con, session)

    def stop(self, session_id):
        with self.transaction() as con:
            session = self._session(con, session_id)
            if session["status"] == "active":
                con.execute("UPDATE sessions SET status='stopped',updated=? WHERE id=?", (self.now.isoformat(), session_id))
                self._event(con, "session_stopped", {"session_id": session_id})
            return self._packet(con, self._session(con, session_id))

    def _evidence(self, con, module, stage=None, since=None):
        targets = {key for key, c in self.catalogue[module].items() if stage is None or c["week"] == stage}
        query = "SELECT * FROM attempts WHERE module=? AND delayed=1 AND verdict IN ('correct','incorrect')"
        args = [module]
        if since:
            query += " AND at>=?"
            args.append(since)
        query += " ORDER BY at,rowid"
        latest = {r["card_id"]: dict(r) for r in con.execute(query, args) if r["card_id"] in targets}
        successful = sum(r["verdict"] == "correct" and not r["assisted"] for r in latest.values())
        total = len(targets)
        return {"expected": total, "tested": len(latest), "successful": successful,
                "coverage": len(latest) / total if total else 0,
                "success_rate": successful / total if total else 0,
                "forgetting_rate": (len(latest) - successful) / len(latest) if latest else None,
                "missing": sorted(targets - latest.keys())}

    def _status(self, con):
        modules = {}
        for module in MODULES:
            plan = self._plan(con, module)
            evidence = self._evidence(con, module)
            due = con.execute("SELECT COUNT(*) FROM cards WHERE module=? AND due<=?", (module, self.now.isoformat())).fetchone()[0]
            learned = con.execute("SELECT COUNT(*) FROM cards WHERE module=?", (module,)).fetchone()[0]
            active = con.execute("SELECT id FROM sessions WHERE module=? AND status='active'", (module,)).fetchone()
            modules[module] = {"plan": plan, "introduced": learned, "due": due,
                               "evidence": evidence, "active_session": active[0] if active else None}
        complete = all(m["plan"]["stage"] == 5 and m["evidence"]["coverage"] == 1 and m["evidence"]["success_rate"] > .9
                       and m["due"] == 0 and m["active_session"] is None for m in modules.values())
        return {"as_of": self.now.isoformat(), "modules": modules, "programme_complete": complete,
                "meaning": "Delayed unassisted recall evidence; FSRS predictions are not measured mastery."}

    def status(self):
        with self.transaction() as con:
            return self._status(con)

    def evaluate(self, module):
        with self.transaction() as con:
            plan = self._plan(con, module)
            require(self.now - utc(plan["last_evaluated"]) >= timedelta(days=7), "period_open", "Seven days have not elapsed since the last plan adjustment.")
            require(con.execute("SELECT 1 FROM sessions WHERE module=? AND status='active'", (module,)).fetchone() is None, "active_session", "Finish or stop this module's active session before evaluating its plan.")
            stage = plan["stage"] if plan["stage"] <= 4 else None
            evidence = self._evidence(con, module, stage, plan["period_start"])
            proposal = decide(plan, evidence)
            evaluation_id = uuid.uuid4().hex[:16]
            payload = {"evaluation_id": evaluation_id, "module": module, "revision": plan["revision"],
                       "evidence": evidence, "proposal": proposal, "period_start": plan["period_start"], "period_end": self.now.isoformat()}
            con.execute("INSERT INTO evaluations VALUES(?,?,?,?,?,0)", (evaluation_id, module, plan["revision"], self.now.isoformat(), encode(payload)))
            self._event(con, "plan_evaluated", {"evaluation_id": evaluation_id, "module": module})
            return payload

    def apply(self, evaluation_id):
        with self.transaction() as con:
            row = con.execute("SELECT * FROM evaluations WHERE id=?", (evaluation_id,)).fetchone()
            require(row is not None, "unknown_evaluation", "Read evaluate to obtain a plan proposal first.")
            if row["applied"]:
                return {"status": "already_applied", "evaluation_id": evaluation_id, "plan": self._plan(con, row["module"])}
            plan = self._plan(con, row["module"])
            require(plan["revision"] == row["revision"], "stale_evaluation", "Plan changed since evaluation. Evaluate again.")
            require(con.execute("SELECT 1 FROM sessions WHERE module=? AND status='active'", (row["module"],)).fetchone() is None, "active_session", "Finish or stop this module's session before applying a plan.")
            payload = json.loads(row["payload"])
            current = self._evidence(con, row["module"], plan["stage"] if plan["stage"] <= 4 else None, plan["period_start"])
            require(current == payload["evidence"], "stale_evidence", "Learning evidence changed. Evaluate again before applying.")
            proposal = decide(plan, current)
            period_start = plan["period_start"] if current["coverage"] < 1 else self.now.isoformat()
            con.execute("UPDATE plans SET stage=?,quota=?,review_factor=?,revision=revision+1,period_start=?,last_evaluated=? WHERE module=?",
                        (proposal["stage"], proposal["quota"], proposal["review_factor"], period_start, self.now.isoformat(), row["module"]))
            con.execute("UPDATE evaluations SET applied=1 WHERE id=?", (evaluation_id,))
            self._event(con, "plan_applied", {"evaluation_id": evaluation_id, "reason": proposal["reason"]})
            return {"status": "applied", "evaluation_id": evaluation_id, "plan": self._plan(con, row["module"]), "reason": proposal["reason"]}

    def _preferences(self, con, module):
        return [dict(r) for r in con.execute("SELECT id,scope,kind,value,reason FROM preferences WHERE status='active' AND scope IN ('all',?) ORDER BY id", (module,))]

    def preference(self, scope, value, reason, supersedes=None):
        require(scope in (*MODULES, "all"), "invalid_scope", "Preference scope must be all or a module.")
        require(isinstance(value, str) and 0 < len(value.strip()) <= 500 and isinstance(reason, str) and 0 < len(reason.strip()) <= 1000,
                "invalid_preference", "Supply a short learner preference and its source/reason.")
        with self.transaction() as con:
            if supersedes is not None:
                old = con.execute("SELECT * FROM preferences WHERE id=?", (supersedes,)).fetchone()
                require(old is not None and old["scope"] == scope and old["status"] == "active", "invalid_supersession", "Only supersede an active preference with the same scope.")
                con.execute("UPDATE preferences SET status='superseded' WHERE id=?", (supersedes,))
            cur = con.execute("INSERT INTO preferences(scope,kind,value,reason,status,created,supersedes) VALUES(?,?,?,?,?,?,?)", (scope, "learner_preference", value, reason, "active", self.now.isoformat(), supersedes))
            self._event(con, "preference_saved", {"id": cur.lastrowid, "scope": scope})
            return {"id": cur.lastrowid, "status": "active", "scope": scope, "value": value, "saved": True,
                    "boundary": "Preferences guide explanations; they do not override grading, evidence or plan rules."}

    def export(self):
        with self.transaction() as con:
            return {"schema": SCHEMA, "content_hash": self.content_hash, "exported_at": self.now.isoformat(),
                    "tables": {table: [dict(row) for row in con.execute(f"SELECT * FROM {table}")] for table in
                               ("meta", "plans", "cards", "sessions", "attempts", "exposures", "preferences", "evaluations", "events")},
                    "notice": "Private learner snapshot. Keep out of Git and shared workshop evidence."}


def decide(plan: dict, evidence: dict) -> dict:
    """Pure outer policy. Boundary cases can be tested without simulating a month."""
    base = BASE_NEW[plan["module"]]
    quota = max(1, math.floor(base * .7)) if evidence["forgetting_rate"] is not None and evidence["forgetting_rate"] > .2 else base
    result = {"stage": plan["stage"], "quota": quota, "review_factor": 1.0, "action": "hold"}
    if evidence["expected"] == 0 or evidence["coverage"] < 1:
        return {**result, "quota": plan["quota"], "review_factor": plan["review_factor"], "reason": "Incomplete delayed-recall coverage; untested items cannot count as success."}
    if plan["stage"] == 5:
        return {**result, "action": "review", "reason": "Continue spaced review; weak cards remain eligible through FSRS."}
    if evidence["success_rate"] > .8:
        return {**result, "stage": plan["stage"] + 1, "action": "advance", "reason": "Full coverage and delayed success above 80%."}
    if evidence["success_rate"] >= .5:
        return {**result, "stage": plan["stage"] + 1, "review_factor": 1.5, "action": "advance_with_review", "reason": "Full coverage and delayed success from 50% through 80%; increase review allocation."}
    return {**result, "reason": "Delayed success below 50%; remain at this stage."}

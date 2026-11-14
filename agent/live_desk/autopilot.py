"""
Autopilot: the Week 11 judge is the gatekeeper; a human only handles what it rejected.

For each company in a run:
    draft            Week 10 composer (v1 original / v2 honest) or the LLM writer (v3), polished
    judge            Week 11 evaluator v0.2.1
    PASS             -> sent automatically (status: sent)
    FAIL             -> the violations become improvement instructions for the LLM writer
                        -> improved email -> final verification by the judge (up to MAX_FIXES rewrites)
                        -> verified : waits for an admin (status: awaiting_approval)
                        -> still failing: blocked (status: blocked); the admin may edit it, it is re-judged
    admin approves   -> re-judged on the server, then sent (status: sent, approved_by recorded)

Every step is appended to the item's timeline, so the admin sees the first draft, the judge's
instructions, the improved email, the final verification and the sent email.

Safety: max items per run (AUTOPILOT_MAX_PER_RUN, default 10), a pause between sends
(AUTOPILOT_SEND_DELAY_S, default 2), a stop button, OUTBOUND_MODE (off = nothing leaves the machine),
and in live mode nothing is auto-sent (there is no recipient on file): every item needs an admin
who types the address.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / ".state" / "autopilot.db"
MAX_FIXES = 2
WRITERS = ("v1", "v2", "v3")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path = DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, run_id TEXT, company TEXT, writer TEXT, "
                        "status TEXT, data TEXT, created TEXT, updated TEXT)")
        self.lock = threading.RLock()

    def add(self, run_id: str, company: str, writer: str) -> str:
        iid = "AP-" + uuid.uuid4().hex[:8]
        with self.lock:
            self.db.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?)",
                            (iid, run_id, company, writer, "queued", json.dumps({"timeline": []}), now(), now()))
        return iid

    def get(self, iid: str) -> dict | None:
        r = self.db.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
        return self._row(r) if r else None

    def items(self, run_id: str | None = None) -> list[dict]:
        q = "SELECT * FROM items" + (" WHERE run_id=?" if run_id else "") + " ORDER BY created DESC, id"
        return [self._row(r) for r in self.db.execute(q, (run_id,) if run_id else ())]

    def step(self, iid: str, kind: str, status: str | None = None, **data) -> None:
        """Append one timeline step (and optionally move the status)."""
        with self.lock:
            it = self.get(iid)
            it["data"]["timeline"].append({"step": kind, "ts": now(), **data})
            self.db.execute("UPDATE items SET data=?, status=COALESCE(?, status), updated=? WHERE id=?",
                            (json.dumps(it["data"], ensure_ascii=False), status, now(), iid))

    def set_status(self, iid: str, status: str, expect: str | None = None) -> bool:
        with self.lock:
            q, args = "UPDATE items SET status=?, updated=? WHERE id=?", [status, now(), iid]
            if expect:
                q += " AND status=?"
                args.append(expect)
            return self.db.execute(q, args).rowcount == 1

    def done_companies(self) -> set[str]:
        return {r[0].lower() for r in self.db.execute("SELECT company FROM items")}

    @staticmethod
    def _row(r) -> dict:
        iid, run_id, company, writer, status, data, created, updated = r
        return {"id": iid, "run_id": run_id, "company": company, "writer": writer, "status": status,
                "data": json.loads(data), "created": created, "updated": updated}


class Autopilot:
    """Runs one batch in a background thread. Dependencies are injected so tests run without network."""

    def __init__(self, store: Store, *, research: Callable, compose: Callable, judge: Callable, rewrite: Callable | None,
                 instructions: Callable, deliver: Callable, outbound_mode: Callable[[], str],
                 send_delay_s: float | None = None):
        self.store, self.research, self.compose, self.judge = store, research, compose, judge
        self.rewrite, self.instructions, self.deliver, self.outbound_mode = rewrite, instructions, deliver, outbound_mode
        self.send_delay_s = float(os.getenv("AUTOPILOT_SEND_DELAY_S", "2")) if send_delay_s is None else send_delay_s
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None
        self.run_id: str | None = None

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self, companies: list[str], writer: str, background: bool = True) -> str:
        if writer not in WRITERS:
            raise ValueError(f"writer must be one of {WRITERS}")
        if self.running():
            raise RuntimeError("a run is already in progress")
        cap = int(os.getenv("AUTOPILOT_MAX_PER_RUN", "10"))
        self.run_id = "RUN-" + uuid.uuid4().hex[:6]
        ids = [self.store.add(self.run_id, c, writer) for c in companies[:cap]]
        self.stop_flag.clear()
        if background:
            self.thread = threading.Thread(target=self._run, args=(ids,), daemon=True)
            self.thread.start()
        else:
            self._run(ids)
        return self.run_id

    def stop(self) -> None:
        self.stop_flag.set()

    def _run(self, ids: list[str]) -> None:
        for iid in ids:
            if self.stop_flag.is_set():
                self.store.step(iid, "stopped", "stopped", note="run stopped by admin before this item")
                continue
            try:
                self.process(iid)
            except Exception as e:  # one bad company must not stop the batch
                self.store.step(iid, "error", "error", error=f"{type(e).__name__}: {e}"[:300])

    def process(self, iid: str) -> None:
        it = self.store.get(iid)
        name, writer = it["company"], it["writer"]
        self.store.set_status(iid, "drafting")
        brief = self.research(name)
        email, by = self.compose(name, brief, writer)
        self.store.step(iid, "draft", by=by, email=email)
        j = self.judge(brief, email)
        self.store.step(iid, "judge", verdict="pass" if j["all_pass"] else "fail", violations=j["violations"],
                        checks={d: c["pass"] for d, c in j["checks"].items()})
        if j["all_pass"]:
            if self.outbound_mode() == "live":
                self.store.step(iid, "needs_recipient", "awaiting_approval",
                                note="live mode: no recipient on file, an admin must type the address")
                return
            self._send(iid, name, email, j, approved_by=None)
            return
        # failed: the judge's findings become instructions for the writer, then a final verification
        attempt, current = 0, email
        while not j["all_pass"] and attempt < MAX_FIXES and self.rewrite is not None:
            attempt += 1
            self.store.set_status(iid, "fixing")
            self.store.step(iid, "instructions", text=self.instructions(j["violations"]), attempt=attempt)
            current, model = self.rewrite(name, brief, current, j["violations"])
            self.store.step(iid, "rewrite", by=model, email=current, attempt=attempt)
            j = self.judge(brief, current)
            self.store.step(iid, "verify", verdict="pass" if j["all_pass"] else "fail", violations=j["violations"],
                            checks={d: c["pass"] for d, c in j["checks"].items()}, attempt=attempt)
        if j["all_pass"]:
            self.store.step(iid, "awaiting_approval", "awaiting_approval",
                            note="the first draft failed; the improved email passed final verification and needs an admin")
        else:
            why = "no LLM writer configured" if self.rewrite is None else f"still failing after {attempt} rewrite(s)"
            self.store.step(iid, "blocked", "blocked", note=f"{why}: cannot be sent until it passes")

    def _send(self, iid: str, name: str, email: dict, j: dict, approved_by: str | None, to: str | None = None) -> dict:
        if self.send_delay_s:
            time.sleep(self.send_delay_s)  # pace sends (provider limits, inbox sanity)
        d = self.deliver(name, email, j, to)
        self.store.step(iid, "send", "sent" if d["status"] in ("sent", "dry_run") else "send_failed",
                        delivery=d, approved_by=approved_by, email=email)
        return d

    # ── admin actions ───────────────────────────────────────────────────
    def approve(self, iid: str, by: str, email: dict | None = None, to: str | None = None) -> dict:
        """Approve an item the judge rejected at first. The email (optionally edited) is re-judged here."""
        it = self.store.get(iid)
        if not it or it["status"] not in ("awaiting_approval", "blocked"):
            return {"ok": False, "error": f"item is {it['status'] if it else 'missing'}, not awaiting approval"}
        final = email or self.final_email(it)
        brief = self.research(it["company"])
        j = self.judge(brief, final)
        if email is not None:
            self.store.step(iid, "admin_edit", by=by, email=final)
            self.store.step(iid, "verify", verdict="pass" if j["all_pass"] else "fail", violations=j["violations"],
                            checks={d: c["pass"] for d, c in j["checks"].items()}, attempt="admin")
        if not j["all_pass"]:
            if it["status"] == "awaiting_approval":
                self.store.set_status(iid, "blocked")
            return {"ok": False, "error": "the judge still rejects this email", "violations": j["violations"]}
        if self.outbound_mode() == "live" and not (to or "").strip():
            return {"ok": False, "error": "live mode: type the recipient address"}
        if not self.store.set_status(iid, "sending", expect=it["status"] if email is None else None):
            return {"ok": False, "error": "already decided"}
        self.store.step(iid, "approved", by=by)
        d = self._send(iid, it["company"], final, j, approved_by=by, to=to)
        return {"ok": d["status"] in ("sent", "dry_run"), "delivery": d}

    def reject(self, iid: str, by: str, reason: str = "") -> dict:
        it = self.store.get(iid)
        if not it or it["status"] not in ("awaiting_approval", "blocked"):
            return {"ok": False, "error": "not awaiting approval"}
        self.store.step(iid, "rejected", "rejected", by=by, reason=reason)
        return {"ok": True}

    @staticmethod
    def final_email(it: dict) -> dict:
        for s in reversed(it["data"]["timeline"]):
            if s.get("email"):
                return s["email"]
        return {}

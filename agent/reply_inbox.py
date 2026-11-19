"""
Reply watcher: reads real replies from your inbox over IMAP and runs the reply step on each one.

Why: the Resend test sender cannot receive mail, so every outgoing email carries Reply-To: REPLY_TO
(agent/outbound.py). Replies land in your own inbox; this watcher picks up the new ones sent to REPLY_TO,
classifies them (webhook_server.classify_reply) and runs booking_policy.handle_reply, which sends the
booking link for a positive reply through the normal outbound mode (off | redirect | live).

    venv/Scripts/python -m agent.reply_inbox            # watch (Ctrl+C to stop)
    venv/Scripts/python -m agent.reply_inbox --once     # one check, then exit

Settings (.env): REPLY_TO, IMAP_HOST (default imap.gmail.com), IMAP_USER, IMAP_PASSWORD (a Gmail App
Password, never the account password), REPLY_POLL_SECONDS (default 15).

It only reads messages addressed to REPLY_TO, never changes read/unread flags (BODY.PEEK), and remembers
handled Message-IDs in .state/replies_seen.txt (gitignored). Replies already in the inbox when the watcher
first starts are recorded as seen without acting, so only new replies trigger anything.
"""
from __future__ import annotations

import argparse
import email
import imaplib
import os
import re
import time
from email.header import decode_header, make_header
from email.utils import parseaddr
from pathlib import Path

from agent import outbound  # noqa: F401  (loads the repo .env)
from agent.booking_policy import handle_reply
from agent.webhook_server import classify_reply

ROOT = Path(__file__).resolve().parent.parent
SEEN = ROOT / ".state" / "replies_seen.txt"
QUOTE_START = re.compile(r"\n[ \t]*(On [^\n]{0,200}?(?:\n[^\n]{0,200}?)?wrote:|-{2,}\s*Original Message|From: )", re.I)


def settings() -> dict:
    return {"reply_to": (os.getenv("REPLY_TO") or "").strip(), "host": os.getenv("IMAP_HOST") or "imap.gmail.com",
            "user": (os.getenv("IMAP_USER") or "").strip(), "password": os.getenv("IMAP_PASSWORD") or "",
            "every": float(os.getenv("REPLY_POLL_SECONDS", "15"))}


def problem(s: dict) -> str | None:
    missing = [k for k, v in (("REPLY_TO", s["reply_to"]), ("IMAP_USER", s["user"]), ("IMAP_PASSWORD", s["password"])) if not v]
    return f"set {', '.join(missing)} in the Conversion Engine .env (see env.example)" if missing else None


def _text(msg: email.message.Message) -> str:
    """The plain-text part of a message (falls back to stripped HTML)."""
    parts = msg.walk() if msg.is_multipart() else [msg]
    plain = html = None
    for p in parts:
        if p.get_content_maintype() == "multipart" or p.get("Content-Disposition", "").startswith("attachment"):
            continue
        raw = p.get_payload(decode=True)
        if raw is None:
            continue
        txt = raw.decode(p.get_content_charset() or "utf-8", errors="replace")
        if p.get_content_type() == "text/plain" and plain is None:
            plain = txt
        elif p.get_content_type() == "text/html" and html is None:
            html = re.sub(r"<[^>]+>", " ", re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", txt))
    return (plain or html or "").replace("\r\n", "\n")


def new_text(body: str) -> str:
    """Only what the person wrote: drop the quoted original and '>' lines."""
    m = QUOTE_START.search("\n" + body)
    if m:
        body = ("\n" + body)[:m.start()]
    lines = [l for l in body.splitlines() if not l.lstrip().startswith(">")]
    return "\n".join(lines).strip()


def parse(raw: bytes) -> dict:
    msg = email.message_from_bytes(raw)
    name, addr = parseaddr(str(make_header(decode_header(msg.get("From", "")))))
    return {"message_id": (msg.get("Message-ID") or "").strip(), "from_email": addr.lower(), "from_name": name,
            "subject": str(make_header(decode_header(msg.get("Subject", "")))), "text": new_text(_text(msg))}


def _seen() -> set[str]:
    return set(SEEN.read_text(encoding="utf-8").split()) if SEEN.exists() else set()


def _mark(ids: list[str]) -> None:
    if ids:
        SEEN.parent.mkdir(exist_ok=True)
        with SEEN.open("a", encoding="utf-8") as fh:
            fh.write("".join(f"{i}\n" for i in ids))


def fetch(s: dict) -> list[dict]:
    """All messages addressed to REPLY_TO (headers + text), newest last. Read-only."""
    box = imaplib.IMAP4_SSL(s["host"])
    try:
        box.login(s["user"], s["password"])
        folder = '"[Gmail]/All Mail"' if "gmail" in s["host"] else "INBOX"
        if box.select(folder, readonly=True)[0] != "OK":
            box.select("INBOX", readonly=True)
        _, data = box.search(None, "TO", f'"{s["reply_to"]}"')
        out = []
        for num in (data[0] or b"").split()[-50:]:
            _, parts = box.fetch(num, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                out.append(parse(raw))
        return out
    finally:
        try:
            box.logout()
        except Exception:
            pass


def check(s: dict, *, baseline: bool = False) -> list[dict]:
    """One pass: handle every reply not handled before. baseline=True only records what is already there."""
    sender = parseaddr(outbound.OutboundConfig.from_env().sender)[1].lower()
    seen, handled, ids = _seen(), [], []
    for m in fetch(s):
        if not m["message_id"] or m["message_id"] in seen:
            continue
        ids.append(m["message_id"])
        if baseline or m["from_email"] == sender or not m["text"]:
            continue
        cls = classify_reply(m["text"])
        first = m["from_name"].split()[0] if m["from_name"].strip() else None
        r = handle_reply(m["from_email"], cls, first_name=first, subject=m["subject"])
        handled.append(r | {"text": m["text"][:120]})
    _mark(ids)
    return handled


def _report(r: dict) -> None:
    d = r.get("delivery") or {}
    sent = f"booking link {d.get('status')} ({d.get('mode')})" if d else "nothing sent"
    print(f"  reply from {outbound.mask(r['from_email'])}: \"{r['text']}\"\n"
          f"    -> class={r['reply_class']}  next={r['next_step']}  {sent}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Watch your inbox for replies and send the booking link after a positive one.")
    ap.add_argument("--once", action="store_true", help="check once and exit")
    args = ap.parse_args()
    s = settings()
    if problem(s):
        raise SystemExit(f"reply watcher: {problem(s)}")
    if not SEEN.exists():
        n = len(check(s, baseline=True)) or len(_seen())
        print(f"first run: {n} existing message(s) to {outbound.mask(s['reply_to'])} recorded as seen; only new replies act.")
    print(f"watching {outbound.mask(s['user'])} for replies to {outbound.mask(s['reply_to'])} every {s['every']:.0f}s "
          f"(outbound mode: {outbound.OutboundConfig.from_env().mode}). Ctrl+C to stop.", flush=True)
    while True:
        try:
            for r in check(s):
                _report(r)
        except (imaplib.IMAP4.error, OSError) as e:
            print(f"  IMAP error: {e}", flush=True)
        if args.once:
            return
        time.sleep(s["every"])


if __name__ == "__main__":
    main()

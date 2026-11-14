"""
Outbound email delivery through Resend, with three explicit modes.

    OUTBOUND_MODE=off       (default) nothing leaves the machine; returns a dry-run result
    OUTBOUND_MODE=redirect  every email goes to DEMO_INBOX; subject and body name the intended recipient
    OUTBOUND_MODE=live      email goes to the real recipient (or the override given at send time)

Settings are read from the repo-root .env (and the legacy tau2-bench/.env), see env.example:
    RESEND_API_KEY   Resend API key
    RESEND_FROM      sender; default "Conversion Engine <onboarding@resend.dev>". Resend's test sender
                     only delivers to the Resend account owner's address. To send to anyone else, verify
                     a domain in Resend and set RESEND_FROM to an address on it.
    DEMO_INBOX       where redirect mode delivers
    ALLOWED_RECIPIENTS  optional comma-separated allowlist for live mode (addresses or @domains)

Back-compat: if OUTBOUND_MODE is unset, OUTBOUND_ENABLED=true means live, anything else means off.
This module only delivers. Whether an email may be sent at all is decided before it gets here
(agent/send_gate.py runs the Week 11 evaluator).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
for _env in (ROOT / ".env", ROOT / "tau2-bench" / ".env"):
    load_dotenv(_env, override=False)

MODES = ("off", "redirect", "live")
DEFAULT_FROM = "Conversion Engine <onboarding@resend.dev>"
UNDELIVERABLE = re.compile(r"@([\w-]+\.)*(example|invalid|test|localhost)$", re.I)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class OutboundConfig:
    mode: str
    api_key: str | None
    sender: str
    demo_inbox: str | None
    allowlist: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "OutboundConfig":
        mode = (os.getenv("OUTBOUND_MODE") or "").strip().lower()
        if not mode:
            mode = "live" if os.getenv("OUTBOUND_ENABLED", "false").lower() == "true" else "off"
        if mode not in MODES:
            raise ValueError(f"OUTBOUND_MODE must be one of {MODES}, got {mode!r}")
        allow = tuple(a.strip().lower() for a in (os.getenv("ALLOWED_RECIPIENTS") or "").split(",") if a.strip())
        return cls(mode=mode, api_key=os.getenv("RESEND_API_KEY") or None,
                   sender=os.getenv("RESEND_FROM") or DEFAULT_FROM,
                   demo_inbox=(os.getenv("DEMO_INBOX") or "").strip() or None, allowlist=allow)

    def public(self) -> dict:
        """Safe to show in a UI: never the key, and the inbox is masked."""
        return {"mode": self.mode, "sender": self.sender, "api_key_set": bool(self.api_key),
                "demo_inbox": mask(self.demo_inbox), "allowlist": list(self.allowlist),
                "ready": self.problem() is None, "problem": self.problem()}

    def problem(self) -> str | None:
        if self.mode == "off":
            return None
        if not self.api_key:
            return "RESEND_API_KEY is not set"
        if self.mode == "redirect" and not (self.demo_inbox and EMAIL.match(self.demo_inbox)):
            return "redirect mode needs DEMO_INBOX set to a valid address"
        return None


def mask(addr: str | None) -> str | None:
    if not addr or "@" not in addr:
        return addr
    user, dom = addr.split("@", 1)
    return f"{user[:2]}{'*' * max(1, len(user) - 2)}@{dom}"


def _allowed(addr: str, allowlist: tuple[str, ...]) -> bool:
    a = addr.lower()
    return not allowlist or any(a == x or (x.startswith("@") and a.endswith(x)) for x in allowlist)


def plan(intended_to: str, cfg: OutboundConfig, override_to: str | None = None) -> dict:
    """Decide where an email would go, without sending. Pure, so the UI can preview it."""
    if cfg.mode == "off":
        return {"deliver": False, "to": None, "why": "OUTBOUND_MODE=off: dry run, nothing is sent"}
    if cfg.problem():
        return {"deliver": False, "to": None, "why": cfg.problem()}
    if cfg.mode == "redirect":
        return {"deliver": True, "to": cfg.demo_inbox, "why": f"redirect mode: delivered to the demo inbox instead of {intended_to}"}
    to = (override_to or intended_to or "").strip()
    if not EMAIL.match(to):
        return {"deliver": False, "to": None, "why": f"not a valid address: {to!r}"}
    if UNDELIVERABLE.search(to):
        return {"deliver": False, "to": None, "why": f"{to} is a reserved/test domain and cannot receive mail"}
    if not _allowed(to, cfg.allowlist):
        return {"deliver": False, "to": None, "why": f"{to} is not in ALLOWED_RECIPIENTS"}
    return {"deliver": True, "to": to, "why": "live mode"}


def _redirect_wrap(subject: str, body: str, intended_to: str, note: str) -> tuple[str, str]:
    banner = (f"[DEMO SEND] Intended recipient: {intended_to}\n{note}\n"
              + "-" * 60 + "\n\n")
    return f"[DEMO -> {intended_to}] {subject}", banner + body


def deliver(intended_to: str, subject: str, body: str, *, override_to: str | None = None,
            note: str = "", cfg: OutboundConfig | None = None, client=None) -> dict:
    """Send one email according to the configured mode. Returns a result dict; never raises on send errors."""
    cfg = cfg or OutboundConfig.from_env()
    p = plan(intended_to, cfg, override_to)
    result = {"mode": cfg.mode, "intended_to": intended_to, "routed_to": p["to"], "why": p["why"],
              "status": None, "message_id": None, "error": None}
    if not p["deliver"]:
        result["status"] = "dry_run" if cfg.mode == "off" else "not_sent"
        return result
    if cfg.mode == "redirect":
        subject, body = _redirect_wrap(subject, body, intended_to, note)
    if client is None:
        import resend
        resend.api_key = cfg.api_key
        client = resend.Emails
    t0 = time.time()
    try:
        resp = client.send({"from": cfg.sender, "to": [p["to"]], "subject": subject, "text": body})
        result["status"] = "sent"
        result["message_id"] = (resp or {}).get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
    except Exception as e:  # surface provider errors (bad key, unverified recipient, rate limit) to the caller
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"[:400]
    result["latency_ms"] = round((time.time() - t0) * 1000)
    return result

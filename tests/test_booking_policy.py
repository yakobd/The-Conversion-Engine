"""Booking policy: no calendar link in the first email; the link is sent only after a positive reply."""
import contextlib
import io

import pytest

from agent import booking_policy as bp
from agent.channel_router import ProspectState, _routers
from agent.live_desk.persona import Persona, polish

URL = "https://cal.com/tenacious/15min"


def persona():
    return Persona(name="Yakob Dereje", title="Research Partner", booking_url=URL, website="gettenacious.com")


@pytest.fixture(autouse=True)
def fresh_routers():
    _routers.clear()
    yield
    _routers.clear()


# ── first email ───────────────────────────────────────────────

@pytest.mark.parametrize("body", [
    "Worth 15 minutes to see whether this is relevant for Acme? http://localhost:3000/yakob/30min",
    "Worth 15 minutes to see whether this is relevant for Acme? → http://localhost:3000/yakob/30min",
    "Is capacity on your roadmap? Here's my calendar: https://cal.com/tenacious/15min",
    "Is capacity on your roadmap?\n\nBook a time here: https://cal.com/tenacious/15min",
])
def test_first_email_link_becomes_a_reply_ask(body):
    out = bp.ask_for_reply(body, URL)
    assert "http" not in out and "calendar" not in out.lower()
    assert out.endswith(bp.REPLY_ASK) and out.count(bp.REPLY_ASK) == 1


def test_existing_reply_ask_is_kept_and_link_dropped():
    out = bp.ask_for_reply("Worth a short call? Just reply if so. https://cal.com/tenacious/15min", URL)
    assert out == "Worth a short call? Just reply if so."


def test_custom_booking_url_is_removed_too():
    out = bp.ask_for_reply("Worth 15 minutes? https://calendly.com/yakob/intro", "https://calendly.com/yakob/intro")
    assert "calendly" not in out and bp.REPLY_ASK in out


def test_email_without_links_is_unchanged():
    body = "Is capacity on your roadmap this year?"
    assert bp.ask_for_reply(body, URL) == body


def test_polished_composer_email_has_no_link():
    from agent.email_agent import generate_outreach_email
    brief = {"prospect": "Acme", "firmographics": {"country_code": "US"}, "icp_classification": {"confidence": "low"}}
    with contextlib.redirect_stdout(io.StringIO()):
        e = polish(generate_outreach_email(brief), persona(), "Ana")
    assert "cal.com" not in e["body"] and "localhost" not in e["body"] and "reply" in e["body"].lower()


def test_send_outreach_email_strips_the_link(monkeypatch):
    from agent import email_agent
    monkeypatch.setattr(email_agent, "TRACE_DIR", __import__("pathlib").Path(__import__("tempfile").mkdtemp()))
    res = email_agent.send_outreach_email(
        "x@y.com", {"prospect": "Acme", "subject": "A question about engineering at Acme",
                    "body": "Is engineering capacity on your roadmap this year?\n\nWorth 15 minutes? "
                            "http://localhost:3000/yakob/30min"}, dry_run=True)
    assert res["status"] == "dry_run_success"


# ── after the reply ───────────────────────────────────────────

def fake_deliver(sent):
    def deliver(to, subject, body, **kw):
        sent.append({"to": to, "subject": subject, "body": body})
        return {"mode": "off", "status": "dry_run", "message_id": None, "error": None, "why": "stub"}
    return deliver


@pytest.mark.parametrize("cls", ["engaged", "curious"])
def test_positive_reply_gets_the_booking_link(cls):
    sent = []
    r = bp.handle_reply("ana@acme.com", cls, first_name="Ana", subject="A question about engineering at Acme",
                        persona=persona(), deliver=fake_deliver(sent))
    assert r["next_step"] == "send_booking_link" and r["state"] == ProspectState.EMAIL_REPLIED.value
    assert len(sent) == 1 and sent[0]["to"] == "ana@acme.com"
    assert sent[0]["subject"] == "Re: A question about engineering at Acme"
    assert f"{URL}?utm_source=email_reply" in sent[0]["body"] and sent[0]["body"].startswith("Hi Ana,")


@pytest.mark.parametrize("cls,step,state", [("hard_no", "opted_out", ProspectState.OPTED_OUT),
                                            ("soft_defer", "human_review", ProspectState.EMAIL_REPLIED),
                                            ("objection", "human_review", ProspectState.EMAIL_REPLIED)])
def test_other_replies_get_no_link(cls, step, state):
    sent = []
    r = bp.handle_reply("ana@acme.com", cls, persona=persona(), deliver=fake_deliver(sent))
    assert r["next_step"] == step and r["state"] == state.value and sent == []


def test_booking_after_reply_is_a_valid_transition():
    from agent.channel_router import route_event
    bp.handle_reply("ana@acme.com", "engaged", persona=persona(), deliver=fake_deliver([]))
    assert route_event("ana@acme.com", "call_booked")["current_state"] == ProspectState.CALL_BOOKED


def test_reply_webhook_reports_next_step(monkeypatch):
    from fastapi.testclient import TestClient
    from agent import outbound, webhook_server
    sent = []
    monkeypatch.setattr(outbound, "deliver", fake_deliver(sent))
    monkeypatch.setattr(webhook_server, "emit", lambda *a, **k: None)
    client = TestClient(webhook_server.app)
    r = client.post("/webhooks/email/reply", json={"from": "ana@acme.com", "from_name": "Ana Lopez",
                                                   "subject": "Re: A question", "text": "Sure, tell me more."})
    assert r.json()["next_step"] == "send_booking_link"
    assert len(sent) == 1 and "utm_source=email_reply" in sent[0]["body"]
    r = client.post("/webhooks/email/reply", json={"from": "bo@acme.com", "text": "Please remove me."})
    assert r.json()["next_step"] == "opted_out" and len(sent) == 1


# ── reply watcher (no network) ────────────────────────────────

def test_second_reply_in_a_thread_goes_to_a_human():
    sent = []
    bp.handle_reply("ana@acme.com", "engaged", persona=persona(), deliver=fake_deliver(sent))
    r = bp.handle_reply("ana@acme.com", "curious", persona=persona(), deliver=fake_deliver(sent))
    assert r["next_step"] == "human_review" and len(sent) == 1


def test_reply_watcher_reads_only_the_new_text():
    from agent.reply_inbox import parse
    raw = (b"From: Ana Lopez <ana@acme.com>\r\nTo: me+replies@gmail.com\r\nSubject: Re: A question about Acme\r\n"
           b"Message-ID: <abc@mail>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
           b"okay, sounds good\r\n\r\nOn Wed, Nov 19, 2026 at 10:00 AM Conversion Engine <\r\n"
           b"onboarding@resend.dev> wrote:\r\n> Worth 15 minutes? Just reply and I'll send over a few times.\r\n")
    m = parse(raw)
    assert m == {"message_id": "<abc@mail>", "from_email": "ana@acme.com", "from_name": "Ana Lopez",
                 "subject": "Re: A question about Acme", "text": "okay, sounds good"}


def test_reply_watcher_handles_new_replies_once(monkeypatch, tmp_path):
    from agent import reply_inbox
    monkeypatch.setattr(reply_inbox, "SEEN", tmp_path / "seen.txt")
    msgs = [{"message_id": "<1>", "from_email": "ana@acme.com", "from_name": "Ana", "subject": "Re: Q", "text": "okay"}]
    monkeypatch.setattr(reply_inbox, "fetch", lambda s: msgs)
    calls = []
    monkeypatch.setattr(reply_inbox, "handle_reply", lambda *a, **k: calls.append((a, k)) or
                        {"from_email": a[0], "reply_class": a[1], "next_step": "send_booking_link"})
    first = reply_inbox.check({}, baseline=False)
    again = reply_inbox.check({})
    assert len(first) == 1 and again == [] and calls[0][0] == ("ana@acme.com", "curious")
    assert calls[0][1]["first_name"] == "Ana"


def test_outbound_sets_reply_to():
    from agent import outbound
    cfg = outbound.OutboundConfig(mode="redirect", api_key="k", sender="CE <onboarding@resend.dev>",
                                  demo_inbox="me@gmail.com", allowlist=(), reply_to="me+replies@gmail.com")
    got = {}

    class Client:
        @staticmethod
        def send(msg):
            got.update(msg)
            return {"id": "m1"}
    assert outbound.deliver("a contact at Acme", "S", "B", cfg=cfg, client=Client)["status"] == "sent"
    assert got["reply_to"] == ["me+replies@gmail.com"] and got["to"] == ["me@gmail.com"]

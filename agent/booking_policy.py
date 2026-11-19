"""
Booking policy: the calendar link is offered only after the prospect replies.

    first email   asks for a reply; any calendar link a writer added is swapped for a reply ask
                  (ask_for_reply, used by live_desk/persona.polish and email_agent.send_outreach_email,
                  so the Week 11 judge sees exactly the text that is sent)
    reply         classified by webhook_server.classify_reply, then next_step():
                    engaged / curious      -> short answer with the booking link (utm_source=email_reply)
                    hard_no                -> opted out, nothing sent
                    soft_defer / objection -> left for a human, no link

The benchmark composers in email_agent.py are untouched: their raw output is what produced the
published Week 11 numbers. This module changes what is SENT, at the sending layer.
"""
from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

REPLY_ASK = "Just reply and I'll send over a few times."
BOOK_ON = {"engaged", "curious"}

_CAL = r"https?://(?:localhost:\d+|(?:www\.)?cal\.com)/\S*"
_LEAD = (r"[ \t]*(?:→|->)?[ \t]*"
         r"(?:(?:(?:here'?s|here is) my calendar|my calendar|book (?:a time|a slot|a call)(?: here)?|booking link)[ \t]*:?[ \t]*)?")


def _link_pattern(booking_url: str | None) -> re.Pattern:
    links = [_CAL]
    if booking_url:
        links.append(re.escape(booking_url.split("?")[0].rstrip("/")) + r"\S*")
    return re.compile(_LEAD + "(?:" + "|".join(links) + ")", re.I)


def ask_for_reply(body: str, booking_url: str | None = None) -> str:
    """Remove calendar links from a first email. The first one becomes a reply ask, unless the email
    already asks for a reply."""
    pat = _link_pattern(booking_url)
    if not pat.search(body):
        return body
    has_ask = re.search(r"\breply\b", pat.sub("", body), re.I) is not None
    state = {"first": True}

    def swap(_m: re.Match) -> str:
        out = f" {REPLY_ASK}" if state["first"] and not has_ask else ""
        state["first"] = False
        return out

    body = pat.sub(swap, body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"(^|\n)[ \t]+", r"\1", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def with_utm(url: str, source: str = "email_reply") -> str:
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query))
    q["utm_source"] = source
    return urlunsplit(parts._replace(query=urlencode(q)))


def next_step(reply_class: str) -> str:
    if reply_class == "hard_no":
        return "opted_out"
    if reply_class in BOOK_ON:
        return "send_booking_link"
    return "human_review"


def booking_reply(persona, first_name: str | None = None, subject: str = "") -> dict:
    """The answer to a positive reply: thanks, the booking link, and a fallback."""
    hi = f"Hi {first_name.strip()}," if first_name and first_name.strip() else "Hi there,"
    subj = (subject or "our conversation").strip()
    if not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"
    body = (f"{hi}\n\nThanks for getting back to me. Here's my calendar, so you can pick a 15-minute slot "
            f"that suits you: {with_utm(persona.booking_url)}\n\n"
            "If none of the times work, just reply with a couple that do.\n\n"
            f"{persona.signature()}\n")
    return {"subject": subj[:78], "body": body}


def handle_reply(from_email: str, reply_class: str, *, first_name: str | None = None, subject: str = "",
                 persona=None, deliver: Callable | None = None) -> dict:
    """Record the reply on the channel state machine and, for a positive reply, send the booking link
    through the configured outbound mode (off | redirect | live)."""
    from agent.channel_router import ProspectState, get_router

    router = get_router(from_email)
    if router.state == ProspectState.NEW:  # a reply proves the first email went out (router state is per process)
        router.on_email_sent()
    if router.state != ProspectState.EMAIL_SENT:  # a later reply in a thread we already answered: a human takes it
        return {"from_email": from_email, "reply_class": reply_class, "next_step": "human_review",
                "state": router.state.value, "why": "conversation already in progress"}
    router.on_email_replied(reply_class)

    step = next_step(reply_class)
    result = {"from_email": from_email, "reply_class": reply_class, "next_step": step, "state": router.state.value}
    if step != "send_booking_link":
        return result

    from agent import outbound  # importing it loads the repo .env (sender name, BOOKING_URL, OUTBOUND_MODE)
    if persona is None:
        from agent.live_desk.persona import Persona
        persona = Persona.from_env()
    if deliver is None:
        deliver = outbound.deliver
    email = booking_reply(persona, first_name, subject)
    d = deliver(from_email, email["subject"], email["body"], note="booking link, sent after the prospect replied")
    result.update(email=email, delivery={k: d.get(k) for k in ("mode", "status", "message_id", "error", "why")})
    return result

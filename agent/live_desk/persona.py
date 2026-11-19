"""
Sender persona + polish: make a composer draft read like an email from a person.

Applied to the draft BEFORE the Week 11 judge sees it (the editor shows the polished text), so what
is judged is exactly what is sent. The benchmark composers themselves are untouched: their outputs
are what produced the published Week 11 numbers.

Settings (.env): SENDER_NAME (max two words, e.g. "Yakob Dereje"), SENDER_TITLE, BOOKING_URL, SENDER_WEBSITE.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

COMPANY = "Tenacious Intelligence Corporation"  # the Week 10 client; the judge recognises its signature lines


@dataclass(frozen=True)
class Persona:
    name: str
    title: str
    booking_url: str
    website: str

    @classmethod
    def from_env(cls) -> "Persona":
        name = " ".join((os.getenv("SENDER_NAME") or "Jordan Blake").split()[:2])  # two words: a sign-off line
        return cls(name=name, title=os.getenv("SENDER_TITLE") or "Research Partner",
                   booking_url=os.getenv("BOOKING_URL") or "https://cal.com/tenacious/15min",
                   website=os.getenv("SENDER_WEBSITE") or "gettenacious.com")

    def signature(self) -> str:
        return f"Best,\n{self.name}\n{self.title}, {COMPANY}\n{self.website}"

    def public(self) -> dict:
        return {"name": self.name, "title": self.title, "booking_url": self.booking_url, "website": self.website}


from agent.booking_policy import ask_for_reply  # noqa: E402

OLD_SIGNATURE = re.compile(r"\n*\s*Research Partner\s*\n\s*Tenacious Intelligence Corporation\s*(\n\s*gettenacious\.com)?\s*$", re.I)
INDUSTRY_LIST = re.compile(r"engineering teams in ([^,.\n]+), ([^,.\n]+?) and could not tell")


def polish(email: dict, persona: Persona, first_name: str | None = None) -> dict:
    subject, body = email.get("subject", "").strip(), email.get("body", "").strip()
    body = INDUSTRY_LIST.sub(lambda m: f"engineering teams at {m.group(1)} and {m.group(2)} companies, and I couldn't tell", body)
    body = ask_for_reply(body, persona.booking_url)  # first email: no calendar link; it is sent after a reply
    body = OLD_SIGNATURE.sub("", body).rstrip()
    if not body.endswith(persona.signature()):
        body = f"{body}\n\n{persona.signature()}"
    if not re.match(r"^(hi|hello|dear|hey)\b", body, re.I):
        body = f"Hi {first_name.strip() if first_name and first_name.strip() else 'there'},\n\n{body}"
    body = re.sub(r"\n{3,}", "\n\n", body)
    return {"subject": subject, "body": body + "\n"}

"""Live send path: Week 11 pre-send gate + Resend delivery modes. No network: Resend is stubbed."""
import contextlib
import io
import json

import pytest

from agent import outbound, send_gate

TB = send_gate.TB_DIR
BRIEFS = TB / "training_data" / "week10_train_briefs.jsonl"
pytestmark = pytest.mark.skipif(not (TB / "scoring_evaluator.py").exists(), reason="Week 11 repo not found (set TB_DIR)")


class FakeResend:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def send(self, params):
        if self.fail:
            raise RuntimeError(self.fail)
        self.sent.append(params)
        return {"id": f"re_{len(self.sent)}"}


def cfg(mode="redirect", key="re_test", inbox="me@gmail.com", allow=()):
    return outbound.OutboundConfig(mode=mode, api_key=key, sender="CE <onboarding@resend.dev>", demo_inbox=inbox, allowlist=tuple(allow))


def rows():
    return [json.loads(l) for l in BRIEFS.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── gate: same verdicts as the published benchmark ──────────────────────

def test_gate_reproduces_benchmark_on_204_briefs():
    from agent.email_agent import generate_outreach_email
    data = rows()
    v1 = sum(send_gate.judge(r["brief"], r["week10_email"])["all_pass"] for r in data)
    with contextlib.redirect_stdout(io.StringIO()):
        v2 = sum(send_gate.judge(r["brief"], generate_outreach_email(r["brief"]))["all_pass"] for r in data)
    assert (v1, v2, len(data)) == (10, 204, 204)  # reports/week10_composer_train_briefs.json


def test_gate_explains_a_stale_funding_claim():
    r = next(r for r in rows() if r["brief"]["prospect"] == "Styloosh")
    j = send_gate.judge(r["brief"], r["week10_email"])
    assert not send_gate.allowed(j) and j["violations"][0]["code"] == "FUNDING_NOT_RECENT"
    assert "older than 180 days" in j["violations"][0]["evidence"]


# ── delivery modes ──────────────────────────────────────────────────────

def test_off_mode_never_calls_provider():
    fake = FakeResend()
    d = outbound.deliver("a@b.com", "s", "b", cfg=cfg(mode="off"), client=fake)
    assert d["status"] == "dry_run" and fake.sent == []


def test_redirect_goes_to_demo_inbox_and_names_intended_recipient():
    fake = FakeResend()
    d = outbound.deliver("Styloosh (prospect contact)", "Hello", "Body", note="PASS", cfg=cfg(), client=fake)
    assert d["status"] == "sent" and d["message_id"] == "re_1"
    sent = fake.sent[0]
    assert sent["to"] == ["me@gmail.com"] and sent["subject"] == "Hello"  # the real subject, untouched
    assert sent["text"].startswith("Body") and "originally addressed to Styloosh" in sent["text"] and "PASS" in sent["text"]


def test_live_mode_uses_typed_address_and_blocks_reserved_domains_and_allowlist():
    fake = FakeResend()
    live = cfg(mode="live", allow=("@gmail.com",))
    assert outbound.deliver("x", "s", "b", override_to="friend@gmail.com", cfg=live, client=fake)["status"] == "sent"
    assert fake.sent[0]["to"] == ["friend@gmail.com"]
    assert outbound.deliver("dana@sunnybowl.example", "s", "b", cfg=cfg(mode="live"), client=fake)["status"] == "not_sent"
    assert outbound.deliver("x", "s", "b", override_to="boss@company.com", cfg=live, client=fake)["status"] == "not_sent"
    assert len(fake.sent) == 1


def test_missing_key_or_inbox_is_reported_not_sent():
    fake = FakeResend()
    assert outbound.deliver("x", "s", "b", cfg=cfg(key=None), client=fake)["why"] == "RESEND_API_KEY is not set"
    assert "DEMO_INBOX" in outbound.deliver("x", "s", "b", cfg=cfg(inbox=None), client=fake)["why"]
    assert fake.sent == []


def test_provider_error_is_returned_not_raised():
    d = outbound.deliver("x", "s", "b", cfg=cfg(), client=FakeResend(fail="403 domain not verified"))
    assert d["status"] == "error" and "domain not verified" in d["error"]


def test_config_never_exposes_the_key_and_masks_inbox(monkeypatch):
    monkeypatch.setenv("OUTBOUND_MODE", "redirect")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret_value")
    monkeypatch.setenv("DEMO_INBOX", "yakob@example.org")
    pub = outbound.OutboundConfig.from_env().public()
    assert "re_secret_value" not in json.dumps(pub) and pub["api_key_set"] is True and pub["demo_inbox"].startswith("ya*")


def test_legacy_outbound_enabled_maps_to_modes(monkeypatch):
    monkeypatch.delenv("OUTBOUND_MODE", raising=False)
    monkeypatch.setenv("OUTBOUND_ENABLED", "false")
    assert outbound.OutboundConfig.from_env().mode == "off"


# ── the desk API: gate enforced server-side ─────────────────────────────

@pytest.fixture()
def desk(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from agent.live_desk import server
    fake = FakeResend()
    monkeypatch.setattr(server, "SEND_LOG", tmp_path / "sends.jsonl")
    monkeypatch.setattr(server, "STATE", tmp_path)
    monkeypatch.setattr(server.outbound.OutboundConfig, "from_env", classmethod(lambda c: cfg()))
    real_deliver = outbound.deliver
    monkeypatch.setattr(server.outbound, "deliver", lambda *a, **k: real_deliver(*a, **{**k, "client": fake}))
    return TestClient(server.app), fake


def test_desk_blocks_failing_email_even_if_client_insists(desk):
    client, fake = desk
    r = client.post("/api/research", json={"name": "Styloosh"}).json()
    s = client.post("/api/send", json={"name": "Styloosh", "email": r["emails"]["v1"], "composer": "v1"})
    assert s.status_code == 409 and s.json()["detail"]["judgment"]["all_pass"] is False and fake.sent == []


def test_desk_sends_passing_email_to_demo_inbox(desk):
    client, fake = desk
    r = client.post("/api/research", json={"name": "Styloosh"}).json()
    s = client.post("/api/send", json={"name": "Styloosh", "email": r["emails"]["v2"], "composer": "v2"}).json()
    assert s["delivery"]["status"] == "sent" and fake.sent[0]["to"] == ["me@gmail.com"]
    assert client.get("/api/sends").json()["sends"][0]["verdict"] == "pass"


def test_send_outreach_email_blocks_on_evaluator_failure():
    from agent.email_agent import send_outreach_email
    r = next(r for r in rows() if r["brief"]["prospect"] == "Styloosh")
    res = send_outreach_email("x@y.com", {**r["week10_email"], "prospect": "Styloosh"}, dry_run=True, brief=r["brief"])
    assert res["status"] == "blocked_by_evaluator" and "FUNDING_NOT_RECENT" in res["judgment"]["violations"]


# ── persona polish + LLM writer (stubbed: no network, no spend) ─────────

def persona():
    from agent.live_desk.persona import Persona
    return Persona(name="Yakob Dereje", title="Research Partner", booking_url="https://cal.com/tenacious/15min",
                   website="gettenacious.com")


def test_polish_reads_like_a_person_and_never_changes_verdicts():
    from agent.live_desk.persona import polish
    from agent.email_agent import generate_outreach_email
    data = rows()
    for r in data:
        before = {v["code"] for v in send_gate.judge(r["brief"], r["week10_email"])["violations"]}
        after = {v["code"] for v in send_gate.judge(r["brief"], polish(r["week10_email"], persona()))["violations"]}
        assert before == after, r["brief"]["prospect"]
    r = next(r for r in data if r["brief"]["prospect"] == "Styloosh")
    with contextlib.redirect_stdout(io.StringIO()):
        e = polish(generate_outreach_email(r["brief"]), persona(), "Ana")
    assert e["body"].startswith("Hi Ana,") and "localhost" not in e["body"] and "Yakob Dereje" in e["body"]
    assert "e-commerce and jewelry companies" in e["body"] and send_gate.judge(r["brief"], e)["all_pass"]


def test_writer_rewrite_uses_the_judges_violations(desk, monkeypatch):
    client, _ = desk
    from agent import llm_writer
    seen = {}

    def fake_write(brief, persona, first_name=None, previous=None, violations=None):
        seen["violations"] = [v["code"] for v in (violations or [])]
        return {"email": {"subject": "A question about Styloosh",
                          "body": "Is engineering capacity on your roadmap? Here's my calendar: https://cal.com/tenacious/15min"},
                "model": "stub", "rewrite": bool(previous)}
    monkeypatch.setattr(llm_writer, "write", fake_write)
    r = client.post("/api/research", json={"name": "Styloosh"}).json()
    w = client.post("/api/write", json={"name": "Styloosh", "email": r["emails"]["v1"]}).json()
    assert seen["violations"] == ["FUNDING_NOT_RECENT"] and w["rewrite"] is True
    assert client.post("/api/judge", json={"name": "Styloosh", "email": w["email"]}).json()["all_pass"]

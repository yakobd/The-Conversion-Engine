"""Autopilot: judge-gated sending with admin approval only for what the judge rejected. All I/O stubbed."""
import pytest

from agent.live_desk.autopilot import Autopilot, Store

GOOD = {"subject": "A question", "body": "Is capacity on your roadmap? https://cal.com/x"}
BAD = {"subject": "Post-funding", "body": "Congrats on the recent funding!"}
FIXED = {"subject": "A question", "body": "Fixed draft. https://cal.com/x"}


def verdict(email):
    ok = email in (GOOD, FIXED) or email.get("body", "").startswith("Edited ok")
    v = [] if ok else [{"dimension": "honesty", "code": "FUNDING_NOT_RECENT", "evidence": "recent funding (brief: older than 180 days)"}]
    return {"all_pass": ok, "violations": v, "evaluator_version": "0.2.1",
            "checks": {"grounding": {"pass": True}, "honesty": {"pass": ok}, "commercial_safety": {"pass": True},
                       "tone": {"pass": True}, "format": {"pass": True}}}


def make(tmp_path, drafts, fixes=None, mode="redirect", fixer=True):
    sent = []
    fixes = list(fixes or [])

    def compose(name, brief, writer):
        return drafts[name], "stub writer"

    def rewrite(name, brief, current, violations):
        return fixes.pop(0), "stub-llm"

    ap = Autopilot(Store(tmp_path / "ap.db"), research=lambda n: {"prospect": n}, compose=compose,
                   judge=lambda brief, email: verdict(email), rewrite=rewrite if fixer else None,
                   instructions=lambda vs: "Fix: " + ", ".join(v["code"] for v in vs),
                   deliver=lambda name, email, j, to: sent.append((name, email, to)) or {"status": "sent", "message_id": "re_1",
                                                                                         "why": "redirect", "routed_to": "me@x"},
                   outbound_mode=lambda: mode, send_delay_s=0)
    return ap, sent


def steps(ap, iid):
    return [s["step"] for s in ap.store.get(iid)["data"]["timeline"]]


def test_perfect_email_is_sent_automatically_without_admin(tmp_path):
    ap, sent = make(tmp_path, {"A": GOOD})
    ap.start(["A"], "v3", background=False)
    it = ap.store.items()[0]
    assert it["status"] == "sent" and steps(ap, it["id"]) == ["draft", "judge", "send"] and sent[0][0] == "A"


def test_failed_email_is_fixed_then_waits_for_admin_and_is_sent_after_approval(tmp_path):
    ap, sent = make(tmp_path, {"B": BAD}, fixes=[FIXED])
    ap.start(["B"], "v1", background=False)
    it = ap.store.items()[0]
    assert it["status"] == "awaiting_approval" and sent == []
    assert steps(ap, it["id"]) == ["draft", "judge", "instructions", "rewrite", "verify", "awaiting_approval"]
    tl = it["data"]["timeline"]
    assert tl[1]["verdict"] == "fail" and "FUNDING_NOT_RECENT" in tl[2]["text"] and tl[4]["verdict"] == "pass"
    r = ap.approve(it["id"], "admin")
    assert r["ok"] and sent[0][1] == FIXED and ap.store.get(it["id"])["status"] == "sent"
    assert steps(ap, it["id"])[-2:] == ["approved", "send"]
    assert ap.approve(it["id"], "admin")["ok"] is False  # cannot be sent twice


def test_still_failing_after_fixes_is_blocked_and_cannot_be_approved(tmp_path):
    ap, sent = make(tmp_path, {"C": BAD}, fixes=[BAD, BAD])
    ap.start(["C"], "v1", background=False)
    it = ap.store.items()[0]
    assert it["status"] == "blocked" and steps(ap, it["id"]).count("rewrite") == 2
    assert ap.approve(it["id"], "admin")["ok"] is False and sent == []


def test_admin_edit_is_rejudged_before_sending(tmp_path):
    ap, sent = make(tmp_path, {"C": BAD}, fixes=[BAD, BAD])
    ap.start(["C"], "v1", background=False)
    iid = ap.store.items()[0]["id"]
    bad_edit = ap.approve(iid, "admin", email={"subject": "x", "body": "still the recent funding"})
    assert bad_edit["ok"] is False and sent == []
    good_edit = ap.approve(iid, "admin", email={"subject": "x", "body": "Edited ok, asking instead"})
    assert good_edit["ok"] and sent[0][1]["body"].startswith("Edited ok")
    assert "admin_edit" in steps(ap, iid)


def test_no_fixer_means_blocked(tmp_path):
    ap, _ = make(tmp_path, {"D": BAD}, fixer=False)
    ap.start(["D"], "v1", background=False)
    assert ap.store.items()[0]["status"] == "blocked"


def test_live_mode_never_auto_sends(tmp_path):
    ap, sent = make(tmp_path, {"E": GOOD}, mode="live")
    ap.start(["E"], "v3", background=False)
    iid = ap.store.items()[0]["id"]
    assert ap.store.get(iid)["status"] == "awaiting_approval" and sent == []
    assert ap.approve(iid, "admin")["ok"] is False                      # needs a typed recipient
    assert ap.approve(iid, "admin", to="friend@gmail.com")["ok"] and sent[0][2] == "friend@gmail.com"


def test_reject_and_run_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_MAX_PER_RUN", "2")
    ap, sent = make(tmp_path, {"A": GOOD, "B": BAD, "C": GOOD}, fixes=[FIXED])
    ap.start(["A", "B", "C"], "v3", background=False)
    items = {i["company"]: i for i in ap.store.items()}
    assert set(items) == {"A", "B"}  # capped at 2
    assert ap.reject(items["B"]["id"], "admin", "not now")["ok"] and ap.store.get(items["B"]["id"])["status"] == "rejected"
    assert [s[0] for s in sent] == ["A"]


def test_bad_writer_value_rejected(tmp_path):
    ap, _ = make(tmp_path, {})
    with pytest.raises(ValueError):
        ap.start(["A"], "v9", background=False)

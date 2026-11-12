"""Honest composer (v2) and signal recency. Run: venv/Scripts/python -m pytest tests/"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.email_agent import generate_outreach_email, generate_outreach_email_v1  # noqa: E402
from agent.enrichment.pipeline import classify_icp_segment  # noqa: E402
from agent.signal_recency import valid_signals  # noqa: E402

SNAP = "2024-07-10"


def brief(**kw):
    b = {"prospect": "Acme", "snapshot_date": SNAP,
         "icp_classification": {"segment": 1, "confidence": "medium", "reasons": []},
         "firmographics": {"company": "Acme", "country_code": "US", "industries": ["Software"]},
         "ai_maturity": {"ai_maturity_score": 1, "confidence": "medium"},
         "layoff_signal": {"layoff_detected": False}, "leadership_signal": {"leadership_change_detected": False},
         "job_post_signal": {"assert_aggressive_hiring": False}, "funding": None}
    b.update(kw)
    return b


def text(e):
    return (e["subject"] + "\n" + e["body"]).lower()


def test_recency_windows():
    assert valid_signals(brief(funding={"announced_on": "2024-03-01"}))["funding"]          # 131 days
    assert not valid_signals(brief(funding={"announced_on": "2014-05-20"}))["funding"]
    assert valid_signals(brief(layoff_signal={"layoff_detected": True, "date": "2024-05-01"}))["layoff"]
    assert not valid_signals(brief(layoff_signal={"layoff_detected": True, "date": "4/2/2020"}))["layoff"]
    assert not valid_signals(brief(leadership_signal={"leadership_change_detected": True, "date": "2024-01-01"}))["leadership"]


def test_raw_w10_format_is_understood():
    raw = brief(snapshot_date=None)
    raw["firmographics"].update({"snapshot_date": SNAP,
                                 "funding_rounds_list": '[{"announced_on": "2024-05-20"}, {"announced_on": "2019-01-01"}]'})
    assert valid_signals(raw)["funding"]


def test_stale_funding_is_not_pitched():
    e = generate_outreach_email(brief(funding={"announced_on": "2014-05-20", "recent": False}))
    assert "post-funding" not in text(e) and "recently raised" not in text(e)
    assert e["segment"] == 0                                   # abstained


def test_v1_shows_the_bug_v2_fixes():
    b = brief(funding={"announced_on": "2014-05-20", "recent": False})
    assert "post-funding" in text(generate_outreach_email_v1(b))


def test_fresh_funding_is_pitched():
    e = generate_outreach_email(brief(funding={"announced_on": "2024-05-01", "recent": True}))
    assert e["segment"] == 1 and "raised funding" in text(e)


def test_layoff_beats_funding_when_both_fresh():
    e = generate_outreach_email(brief(funding={"announced_on": "2024-05-01", "recent": True},
                                      layoff_signal={"layoff_detected": True, "date": "2024-06-01", "within_window": True}))
    assert e["segment"] == 2 and "restructuring" in text(e)


def test_very_low_confidence_abstains():
    b = brief(funding={"announced_on": "2024-05-01", "recent": True})
    b["icp_classification"]["confidence"] = "very_low"
    e = generate_outreach_email(b)
    assert e["segment"] == 0 and "rather ask than guess" in text(e)


@pytest.mark.parametrize("cc,bad", [("DE", "us time zones"), ("KE", "us time zones"), ("US", "cet")])
def test_region_aware_overlap(cc, bad):
    b = brief()
    b["firmographics"]["country_code"] = cc
    assert bad not in text(generate_outreach_email(b))


def test_segment4_never_says_bench():
    e = generate_outreach_email(brief(ai_maturity={"ai_maturity_score": 2, "confidence": "high"}))
    assert e["segment"] == 4 and "bench" not in text(e)


def test_classifier_ignores_stale_signals():
    icp = classify_icp_segment({"funding_rounds_list": '[{"announced_on": "2014-05-20"}]', "snapshot_date": SNAP},
                               {"layoff_detected": True, "latest_layoff": {"key_event_date": "2020-04-02"}},
                               {"leadership_change_detected": False}, {"ai_maturity_score": 0})
    assert icp["segment"] is None and icp["confidence"] == "very_low"
    assert any("older than 180 days" in r for r in icp["reasons"])

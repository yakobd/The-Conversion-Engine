"""
Signal recency: decide which hiring signals are VALID to pitch on.

The challenge defines the buying windows:
  funding     Series A/B in the last 180 days  -> Segment 1
  layoff      in the last 120 days             -> Segment 2
  leadership  new CTO / VP Eng in last 90 days -> Segment 3
Week 10 v1 ignored the dates, so a 2014 funding round or a 2020 layoff was
pitched as "recent" (measured in Tenacious-Bench v0.2: of 32 funding / 14 layoff /
8 leadership signals on fresh companies, 1 / 0 / 1 were inside the window).

Recency is measured from the data's own snapshot date (the Crunchbase scrape
date) when known, otherwise from `as_of` (default: today).

Accepts both brief formats:
  raw W10 brief      firmographics.funding_rounds_list (JSON string), layoff_signal.latest_layoff,
                     leadership_signal.hires
  compact brief      funding {announced_on, recent}, layoff_signal {date, within_window},
                     leadership_signal {date, within_window}, snapshot_date
"""
from __future__ import annotations

import json
from datetime import datetime

WINDOWS = {"funding": 180, "layoff": 120, "leadership": 90}


def _parse(d) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(d)[:19], fmt)
        except (ValueError, TypeError):
            continue
    return None


def _latest_funding_date(brief: dict):
    f = brief.get("funding")
    if isinstance(f, dict) and f.get("announced_on"):
        return f["announced_on"]
    raw = (brief.get("firmographics") or {}).get("funding_rounds_list") or "[]"
    try:
        rounds = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        rounds = []
    dates = [r.get("announced_on") for r in rounds if isinstance(r, dict) and r.get("announced_on")]
    return max(dates) if dates else None


def _event_date(signal: dict, key_list: str):
    if not signal:
        return None
    if signal.get("date"):
        return signal["date"]
    latest = signal.get("latest_layoff") or {}
    if latest.get("key_event_date") or latest.get("date"):
        return latest.get("key_event_date") or latest.get("date")
    items = signal.get(key_list) or []
    dates = [h.get("key_event_date") for h in items if isinstance(h, dict) and h.get("key_event_date")]
    return max(dates) if dates else None


def _recent(precomputed, date, window, as_of) -> bool | None:
    if isinstance(precomputed, bool):
        return precomputed
    d = _parse(date)
    if d is None or as_of is None:
        return None
    return 0 <= (as_of - d).days <= window


def valid_signals(brief: dict, as_of: datetime | None = None) -> dict:
    """{'funding': bool, 'layoff': bool, 'leadership': bool, 'any': bool, 'as_of': str}.
    A signal is valid only if it exists AND its date is inside the window."""
    snap = _parse(brief.get("snapshot_date") or (brief.get("firmographics") or {}).get("snapshot_date"))
    ref = snap or as_of or datetime.now()
    lay = brief.get("layoff_signal") or {}
    lead = brief.get("leadership_signal") or {}
    fund_date = _latest_funding_date(brief)
    f = brief.get("funding") if isinstance(brief.get("funding"), dict) else {}
    out = {
        "funding": bool(fund_date) and bool(_recent(f.get("recent"), fund_date, WINDOWS["funding"], ref)),
        "layoff": bool(lay.get("layoff_detected")) and bool(_recent(lay.get("within_window"), _event_date(lay, "events"), WINDOWS["layoff"], ref)),
        "leadership": bool(lead.get("leadership_change_detected")) and bool(
            _recent(lead.get("within_window"), _event_date(lead, "hires"), WINDOWS["leadership"], ref)),
        "as_of": ref.strftime("%Y-%m-%d"),
    }
    out["any"] = out["funding"] or out["layoff"] or out["leadership"]
    return out

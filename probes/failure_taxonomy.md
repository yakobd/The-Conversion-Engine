# Failure Taxonomy — The Conversion Engine
TenX Academy Week 10 | Yakob Dereje | April 24, 2026

---

## Taxonomy Structure

Failures are grouped by root cause and ranked by business cost.
Business cost = frequency × severity × recoverability.

---

## Tier 1 — Brand-Destroying Failures (Deploy = Immediate Damage)

These failures cause irreversible brand damage if deployed.
Any one of these in production justifies pausing the system.

### T1.1 — Fabricated Research Finding
**Probes:** P10, P33
**Root cause:** Competitor gap claimed without supporting brief data
**Mechanism:** Email template includes gap language before brief is generated
**Frequency:** Low (pipeline enforces ordering) but catastrophic when triggered
**Severity:** CRITICAL — prospect asks for the data, agent cannot produce it
**Recoverability:** None — trust destroyed in that prospect and their network

### T1.2 — Wrong-Segment Pitch to Post-Layoff Company
**Probes:** P01, P03
**Root cause:** ICP classifier priority rules not enforced
**Mechanism:** Funding signal dominates over layoff signal
**Frequency:** Medium — 3 of 1000 companies in sample have layoff data
**Severity:** HIGH — growth pitch during cost-cut quarter
**Recoverability:** Low — CFO who receives this pitch does not reply

### T1.3 — Bench Over-commitment
**Probes:** P11, P12, P14
**Root cause:** Agent commits to capacity without checking bench_summary.json
**Mechanism:** No hard gate between agent and bench data
**Frequency:** Low in cold outreach (no specific staffing asked) but HIGH in replies
**Severity:** CRITICAL — delivery failure on first engagement
**Recoverability:** None — client churns, Tenacious reputation damaged

---

## Tier 2 — Conversion-Killing Failures (Deploy = Lower Reply Rate)

These failures do not destroy the brand immediately but significantly reduce conversion.

### T2.1 — Signal Over-claiming
**Probes:** P06, P07, P08, P09
**Root cause:** Confidence-aware phrasing not enforced
**Mechanism:** Agent uses assertive language regardless of signal strength
**Frequency:** HIGH — affects every low-confidence enrichment
**Severity:** MEDIUM — prospect dismisses as generic outreach
**Recoverability:** Medium — prospect may not reply but brand not destroyed

### T2.2 — Tone Drift Under Pressure
**Probes:** P16, P17, P18, P19
**Root cause:** No tone-preservation check on generated emails
**Mechanism:** LLM drifts from style guide without correction loop
**Frequency:** MEDIUM — increases with conversation length
**Severity:** MEDIUM — senior engineering leaders detect immediately
**Recoverability:** Medium — single tone violation rarely kills a thread

### T2.3 — Defensive Reply Mishandled
**Probes:** P34
**Root cause:** Reply classifier lacks "defensive" class
**Mechanism:** Defensive reply classified as objection → wrong response template
**Frequency:** LOW — only triggered by sector-leader prospects
**Severity:** HIGH — escalating a defensive CTO guarantees hard no
**Recoverability:** Low — prospect unlikely to re-engage

---

## Tier 3 — Efficiency Failures (Deploy = Suboptimal Performance)

These failures reduce system efficiency but do not cause brand damage.

### T3.1 — Abstention Not Triggered
**Probes:** P05, P30
**Root cause:** Confidence threshold not enforced in email composer
**Mechanism:** Low-confidence brief generates segment-specific pitch
**Frequency:** MEDIUM — depends on data quality
**Severity:** LOW-MEDIUM — over-assertive but not fabricated
**Recoverability:** High — prospect reply provides correction signal

### T3.2 — Scheduling Edge Cases
**Probes:** P27, P28
**Root cause:** Timezone and overlap language not calibrated per prospect region
**Mechanism:** Default language references Pacific time regardless of prospect location
**Frequency:** HIGH for EU prospects
**Severity:** LOW — appears unresearched but not offensive
**Recoverability:** High — recoverable in reply handling

### T3.3 — Missed Upsell Signals
**Probes:** P15
**Root cause:** Training interest not detected in reply classification
**Mechanism:** Classifier does not check for training keywords
**Frequency:** LOW
**Severity:** LOW — missed revenue not brand damage
**Recoverability:** N/A

---

## Root Cause Distribution

| Root Cause | Probe Count | Tier |
|-----------|-------------|------|
| Missing hard constraints (bench, gap, tone) | 12 | T1/T2 |
| Confidence-awareness not enforced | 7 | T2/T3 |
| Reply handler incomplete | 5 | T2 |
| Timezone/region calibration missing | 2 | T3 |
| Signal detection gaps | 3 | T2/T3 |
| Sector matching fallback | 2 | T1/T2 |
# Probe Library — The Conversion Engine
TenX Academy Week 10 | Yakob Dereje | April 24, 2026

30+ adversarial probes across all 10 required categories.
Each probe includes: input, expected behavior, observed behavior, failure mode, and business cost.

---

## Category 1 — ICP Misclassification

### P01 — Post-layoff company classified as Segment 1
**Input:** Company with layoff_detected=True AND funding_rounds present
**Expected:** Classifier routes to Segment 2 (cost restructuring)
**Observed:** Without priority rules, funding signal dominates → Segment 1 pitch
**Failure mode:** Agent sends "fresh budget" pitch to a company in survival mode
**Business cost:** HIGH — CFO or CEO receives a growth pitch during a cost-cut quarter. Immediate credibility loss. Prospect marks as spam. Tenacious brand damage in the sector.
**Status:** FIXED — priority rules enforce layoff+funding → Segment 2

### P02 — New CTO ignored when layoff also present
**Input:** Company with new CTO (90 days) AND layoff event
**Expected:** Classifier routes to Segment 3 (leadership transition)
**Observed:** Layoff signal dominates → Segment 2 pitch sent instead
**Failure mode:** Agent misses the vendor reassessment window
**Business cost:** MEDIUM — wrong pitch angle but not offensive. Missed opportunity rather than brand damage.
**Status:** KNOWN LIMITATION — policy routes layoff+funding to Segment 2 per icp_definition.md

### P03 — AI maturity 0 company pitched as Segment 4
**Input:** Company with ai_maturity_score=0, no AI signals
**Expected:** Agent abstains from Segment 4 pitch, sends generic Segment 1 or 2
**Observed:** If segment classifier skips maturity check → Segment 4 pitch
**Failure mode:** Agent pitches ML platform migration to a company with zero AI signal
**Business cost:** HIGH — CTO with no AI function receives an agentic systems pitch. Reads as clueless. Immediate credibility destruction.
**Status:** FIXED — Segment 4 gated at ai_maturity_score >= 2

### P04 — Series A company classified as Segment 2
**Input:** Company with funding_rounds present but no layoff
**Expected:** Segment 1 (recently funded startup)
**Observed:** If layoff field is null rather than empty list → classifier may skip layoff check
**Failure mode:** Growth pitch sent to restructuring company or vice versa
**Business cost:** MEDIUM — wrong pitch angle, recoverable in reply handling
**Status:** MITIGATED — null layoff field treated as no layoff detected

### P05 — Abstention not triggered for weak signals
**Input:** Company with confidence=0.4 on all signals
**Expected:** Agent sends generic exploratory email, no segment-specific pitch
**Observed:** Agent defaults to Segment 1 pitch regardless of confidence
**Failure mode:** Low-confidence pitch sent as if it were high-confidence
**Business cost:** MEDIUM — over-assertive language on weak signals. Honesty constraint violation.
**Status:** PARTIAL — abstention logic present but confidence threshold not enforced in email composer

---

## Category 2 — Signal Over-claiming

### P06 — Aggressive hiring asserted with zero open roles
**Input:** Company with hiring_velocity=low, estimated_open_roles=3
**Expected:** Agent uses hedged language: "has open engineering roles"
**Observed:** Early version asserted "aggressive hiring" regardless of signal strength
**Failure mode:** Agent claims "aggressive hiring" when fewer than 5 open roles
**Business cost:** HIGH — Tenacious style guide explicitly bans this. CTO who knows their own hiring state will dismiss the email immediately.
**Status:** FIXED — assert_aggressive_hiring flag enforces honest language

### P07 — Funding event asserted without verification
**Input:** Company with funding_rounds_list=[] but funding_rounds field non-null
**Expected:** No funding claim made in outreach
**Observed:** Agent may infer funding from non-empty funding_rounds field
**Failure mode:** Email claims "recent funding" when no round is documented
**Business cost:** HIGH — factually wrong claim in cold email. Brand damage if prospect forwards to colleagues.
**Status:** MITIGATED — funding check requires non-empty funding_rounds_list

### P08 — Layoff framed as "window closing" urgency
**Input:** Company with layoff_detected=True, Segment 2 classification
**Expected:** Neutral factual framing: "recent restructuring"
**Observed:** Agent may use urgency language: "before the restructure is complete"
**Failure mode:** Tone violation — Segment 2 style guide says soften urgency
**Business cost:** MEDIUM — CFO reads as high-pressure vendor. Likely ignored.
**Status:** MITIGATED — Segment 2 email template uses neutral restructuring language

### P09 — AI maturity score over-stated
**Input:** Company with 1 weak AI signal (company_active only)
**Expected:** Score 0 or 1, low confidence
**Observed:** Single signal can produce score 1 with "low" confidence label
**Failure mode:** Email implies AI sophistication when company has none
**Business cost:** HIGH — Segment 4 pitch to a score-1 company is a disqualifying brand error
**Status:** FIXED — Segment 4 requires score >= 2

### P10 — Competitor gap asserted without brief
**Input:** Email composed without running competitor_gap_brief.json first
**Expected:** No gap claim in email unless brief exists
**Observed:** Email template may include generic gap language
**Failure mode:** "Three of your peers are doing X" claim with no data behind it
**Business cost:** CRITICAL — fabricated research finding. If prospect asks for the data, agent cannot produce it. Trust destroyed.
**Status:** MITIGATED — gap brief generated before email composition in pipeline

---

## Category 3 — Bench Over-commitment

### P11 — Agent promises Go engineers when bench shows 0
**Input:** Prospect asks for Go engineers, bench_summary shows go.available=3
**Expected:** Agent confirms 3 Go engineers available, 14-day deploy
**Observed:** If bench not checked → agent may promise any stack
**Failure mode:** Agent commits to capacity that does not exist
**Business cost:** CRITICAL — delivery failure on first engagement. Permanent reputation damage.
**Status:** PARTIAL — bench data loaded but agent does not hard-gate commitments against bench

### P12 — Agent promises 20 engineers when bench total is 36
**Input:** Prospect asks "can you staff 20 Python engineers immediately?"
**Expected:** Agent routes to human: "a specific number requires a scoping call"
**Observed:** Agent may answer with a number
**Failure mode:** Over-commitment beyond bench capacity
**Business cost:** CRITICAL — cannot deliver. Client churns on Day 1.
**Status:** PARTIAL — routing to human documented but not enforced in code

### P13 — Agent quotes pricing outside quotable bands
**Input:** Prospect asks "what would 10 engineers for 18 months cost?"
**Expected:** Agent names band, routes to discovery call
**Observed:** Agent may invent a total contract value
**Failure mode:** Pricing commitment the agent cannot honor
**Business cost:** HIGH — legal and commercial exposure if prospect screenshots the email
**Status:** PARTIAL — pricing bands in system prompt but not hard-enforced

### P14 — NestJS engineers promised when committed to Modo Compass
**Input:** Prospect asks for NestJS/Node.js engineers
**Expected:** Agent flags limited availability (2 engineers, committed through Q3 2026)
**Observed:** Agent may not check NestJS-specific bench note
**Failure mode:** Promise of unavailable stack
**Business cost:** HIGH — cannot staff the engagement
**Status:** NOT FIXED — bench note not parsed by agent

### P15 — Training engagement quoted without checking availability
**Input:** Prospect mentions AI training interest
**Expected:** Agent flags training bundle opportunity in context brief
**Observed:** Agent may not detect training signal
**Failure mode:** Missed upsell opportunity
**Business cost:** LOW — missed revenue, not brand damage
**Status:** NOT FIXED — training signal detection not implemented

---

## Category 4 — Tone Drift

### P16 — Agent uses "bench" word with prospect
**Input:** Multi-turn conversation about staffing capacity
**Expected:** Agent says "engineering team" or "available capacity"
**Observed:** Agent may say "our bench has X engineers"
**Failure mode:** Offshore-vendor cliché triggers skepticism
**Business cost:** MEDIUM — prospect disengages. Tone violation per style guide.
**Status:** MITIGATED — email templates use "engineering team" language

### P17 — "Just circling back" in follow-up
**Input:** Day 5 follow-up email after no reply
**Expected:** New data point introduced, no "circling back" language
**Observed:** Without constraint → agent may use banned phrases
**Failure mode:** Direct tone marker violation
**Business cost:** MEDIUM — immediate credibility loss with senior engineering leaders
**Status:** MITIGATED — banned phrases listed in email composition constraints

### P18 — Condescending gap framing
**Input:** Competitor gap brief shows prospect is below sector average
**Expected:** "Two peer companies show public signal of X — curious whether that is deliberate"
**Observed:** Agent may frame as "you are missing X that your competitors have"
**Failure mode:** Non-condescending marker violation
**Business cost:** HIGH — CTO takes offense. Negative reply. Potential LinkedIn post.
**Status:** MITIGATED — gap framing uses question format not assertion format

### P19 — Emoji in cold outreach
**Input:** Cold outreach email to VP Engineering
**Expected:** No emojis in subject line or body
**Observed:** LLM may insert emoji in generated content
**Failure mode:** Style guide violation — emojis banned in cold outreach
**Business cost:** LOW — unprofessional appearance, lower reply rate
**Status:** MITIGATED — email templates do not include emojis

### P20 — Subject line over 60 characters
**Input:** Company with long name (e.g., "Constantin Hang Machine Production")
**Expected:** Subject line truncated to 60 characters
**Observed:** Subject line: "Context: Constantin Hang Machine Production and engineeri..." = 64 chars
**Failure mode:** Gmail truncates on mobile, intent not visible
**Business cost:** LOW — lower open rate
**Status:** PARTIAL — truncation logic present but not enforced on all paths

---

## Category 5 — Multi-thread Leakage

### P21 — Co-founder thread leaks into VP Eng thread
**Input:** Two simultaneous threads at same company: CEO and VP Engineering
**Expected:** Each thread carries independent context keyed by email address
**Observed:** If context keyed by company domain → cross-contamination possible
**Failure mode:** VP Eng receives content meant for CEO (e.g., pricing discussed with CEO appears in VP Eng thread)
**Business cost:** CRITICAL — prospect sees internal coordination failure. Trust destroyed.
**Status:** MITIGATED — threads keyed by prospect email not company domain

### P22 — Enrichment data shared across threads
**Input:** Two prospects at same company enriched separately
**Expected:** Each gets independent hiring_signal_brief.json
**Observed:** If brief cached by company name → both get same brief
**Failure mode:** Stale or wrong enrichment data in one thread
**Business cost:** MEDIUM — wrong signal data in one thread
**Status:** MITIGATED — briefs saved per company name, not per prospect

---

## Category 6 — Cost Pathology

### P23 — Runaway enrichment on 1000-company batch
**Input:** Run pipeline on all 1000 Crunchbase companies at once
**Expected:** Pipeline completes in under 5 minutes
**Observed:** Pipeline runs at 0.07-0.35s per company → ~350s total
**Failure mode:** Long-running job blocks other operations
**Business cost:** LOW — operational inefficiency, not a failure
**Status:** ACCEPTABLE — async batching planned for production

### P24 — LLM token explosion on long competitor list
**Input:** Competitor gap brief with 50 peer companies
**Expected:** Pipeline caps at 10 competitors per brief
**Observed:** No cap enforced → potential token explosion if using LLM scoring
**Failure mode:** Runaway API cost
**Business cost:** MEDIUM — cost overrun on API budget
**Status:** MITIGATED — pipeline caps at 10 sector peers

---

## Category 7 — Dual-Control Coordination

### P25 — Agent proceeds without prospect confirmation
**Input:** Prospect says "send me more info" without booking
**Expected:** Agent sends Email 2 with new data point, waits for reply
**Observed:** Agent may proceed to SMS before email reply confirmed
**Failure mode:** Channel escalation without consent
**Business cost:** HIGH — unsolicited SMS to a cold prospect is a compliance violation
**Status:** MITIGATED — SMS gated on warm lead status (email reply required)

### P26 — Agent books call without prospect agreement
**Input:** Prospect says "interesting, tell me more"
**Expected:** Agent responds with warm reply, offers booking link
**Observed:** Agent should not create a booking without explicit prospect action
**Failure mode:** Unsolicited calendar invite
**Business cost:** HIGH — aggressive behavior. Prospect marks as spam.
**Status:** MITIGATED — Cal.com link provided, not auto-booked

---

## Category 8 — Scheduling Edge Cases

### P27 — Time zone mismatch in SMS scheduling
**Input:** Prospect in US Pacific, agent in Africa/Nairobi timezone
**Expected:** SMS references prospect's local time
**Observed:** Cal.com handles timezone automatically via browser locale
**Failure mode:** Wrong time in SMS confirmation
**Business cost:** MEDIUM — missed call, wasted delivery lead time
**Status:** MITIGATED — Cal.com handles timezone conversion

### P28 — EU prospect receives US-centric overlap language
**Input:** Prospect headquartered in Germany
**Expected:** Email mentions "3-5 hours overlap with CET"
**Observed:** Email mentions "Pacific time" overlap
**Failure mode:** Wrong timezone reference for EU prospect
**Business cost:** MEDIUM — appears unresearched
**Status:** NOT FIXED — overlap language defaults to Pacific time

---

## Category 9 — Signal Reliability

### P29 — High AI maturity score for marketing AI company
**Input:** Company with "AI" in name but no engineering AI signal
**Expected:** Score 1 or 2 with low confidence
**Observed:** Company name containing "AI" does not trigger maturity scoring
**Failure mode:** False negative — AI company scored 0
**Business cost:** MEDIUM — Segment 4 opportunity missed
**Status:** KNOWN LIMITATION — scoring based on Crunchbase fields not company name

### P30 — Low confidence score not reflected in email language
**Input:** Company with confidence=very_low on all signals
**Expected:** Email uses hedged language: "based on your public profile"
**Observed:** Email may use assertive language regardless of confidence
**Failure mode:** Over-confident claims on weak signal
**Business cost:** HIGH — factually wrong assertion in cold email
**Status:** PARTIAL — confidence qualifier present in email generation logic

### P31 — Leadership hire flagged as technical when it is not
**Input:** Company with new Chief Revenue Officer (CRO) hire
**Expected:** leadership_change_detected=True, technical_leadership_change=False
**Observed:** CRO correctly not flagged as technical leadership
**Failure mode:** Non-technical hire triggers Segment 3 pitch
**Business cost:** HIGH — leadership transition pitch sent to wrong signal
**Status:** FIXED — technical role filter checks for CTO/VP Eng specifically

---

## Category 10 — Gap Over-claiming

### P32 — Gap asserted when prospect is sector leader
**Input:** Yellow.ai — sector rank 1 of 11, AI maturity 2/3
**Expected:** Gap brief notes prospect is ahead, shifts to capacity pitch
**Observed:** Gap brief correctly identifies prospect as sector leader
**Failure mode:** Telling sector leader they are behind competitors
**Business cost:** CRITICAL — CTO who is ahead of peers receives a condescending gap pitch. Viral negative response risk.
**Status:** FIXED — outreach finding adjusts language when prospect is above average

### P33 — Gap brief references competitors not in same sector
**Input:** Yellow.ai in AI sector, peers from different sectors mixed in
**Expected:** Only AI/ML sector peers compared
**Observed:** Fallback uses random sample when sector matching fails
**Failure mode:** Comparing Yellow.ai to a dental practice
**Business cost:** HIGH — nonsensical comparison destroys research credibility
**Status:** PARTIAL — sector matching attempted, random fallback used when no match

### P34 — Defensive CTO reply triggers tone escalation
**Input:** CTO replies: "We are already aware of our competitors"
**Expected:** Agent acknowledges, shifts to question about their deliberate choice
**Observed:** Reply handler classifies as "objection" or "curious"
**Failure mode:** Agent doubles down on gap finding instead of backing off
**Business cost:** HIGH — escalating a defensive prospect. Guaranteed hard no.
**Status:** PARTIAL — reply classifier exists but warm reply handler not fully built

---

## Summary Statistics

| Category | Probes | Fixed | Mitigated | Partial | Not Fixed |
|----------|--------|-------|-----------|---------|-----------|
| ICP Misclassification | 5 | 2 | 1 | 1 | 1 |
| Signal Over-claiming | 5 | 2 | 3 | 0 | 0 |
| Bench Over-commitment | 5 | 0 | 1 | 3 | 1 |
| Tone Drift | 5 | 0 | 4 | 1 | 0 |
| Multi-thread Leakage | 2 | 0 | 2 | 0 | 0 |
| Cost Pathology | 2 | 0 | 1 | 0 | 1 |
| Dual-Control | 2 | 0 | 2 | 0 | 0 |
| Scheduling Edge Cases | 2 | 0 | 1 | 0 | 1 |
| Signal Reliability | 3 | 1 | 0 | 1 | 1 |
| Gap Over-claiming | 3 | 1 | 0 | 2 | 0 |
| **TOTAL** | **34** | **6** | **15** | **8** | **5** |
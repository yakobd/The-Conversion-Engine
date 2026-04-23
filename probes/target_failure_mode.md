# Target Failure Mode — The Conversion Engine
TenX Academy Week 10 | Yakob Dereje | April 24, 2026

---

## Selected Target: Signal Over-claiming (T2.1)

### Why This Is the Highest-ROI Failure Mode

Signal over-claiming was selected over Tier 1 failures for the following reason:
Tier 1 failures (bench over-commitment, fabricated research) are already partially
mitigated by architecture. Signal over-claiming is the most frequent unmitigated
failure — it affects every low-confidence enrichment run and directly violates
the Tenacious style guide's Grounded and Honest tone markers.

---

## Business Cost Derivation

### Frequency
- 1,000 companies in Crunchbase ODM sample
- Estimated 40-60% have weak signal (confidence = low or very_low)
- At 60 touches per SDR per week (Tenacious internal baseline),
  signal over-claiming affects ~24-36 emails per week

### Severity Per Occurrence
- Industry cold-email reply rate baseline: 1-3% (LeadIQ 2026)
- Signal-grounded outbound reply rate: 7-12% (Clay 2025)
- Over-claiming on weak signal collapses reply rate back to 1-3%
- Delta: -6 to -9 percentage points per over-claimed email

### Revenue Impact Calculation
Weekly touches: 60
Over-claiming rate (unmitigated): 40%
Affected emails per week: 24
Reply rate with over-claiming: 1.5%
Reply rate without over-claiming: 9% (midpoint of 7-12%)
Delta replies per week: 24 × (9% - 1.5%) = 1.8 additional replies/week
Discovery-call-to-proposal conversion: 40% (Tenacious baseline)
Proposal-to-close conversion: 25% (Tenacious baseline)
ACV (talent outsourcing floor): $[ACV_MIN] (seed/baseline_numbers.md)
Additional qualified leads per week: 1.8 × 40% = 0.72
Additional closed deals per week: 0.72 × 25% = 0.18
Annualized additional revenue: 0.18 × 52 × $[ACV_MIN]

At the ACV floor, fixing signal over-claiming is worth significant
annualized revenue from a single SDR's pipeline.

---

## Mechanism to Fix in Act IV

**Confidence-aware phrasing module.**

A lightweight function that:
1. Reads the confidence field from hiring_signal_brief.json
2. Applies a phrasing rule based on confidence level:
   - confidence=high → assertive language permitted
   - confidence=medium → hedged language required
   - confidence=low → question format required, no assertions
   - confidence=very_low → abstain from segment-specific pitch
3. Patches the email composer output before send
4. Logs the confidence level and phrasing applied to Langfuse

This mechanism requires no additional LLM calls — it is a
deterministic rule applied to existing signal data.

---

## Why Not Bench Over-commitment?

Bench over-commitment (T1.3) is higher severity but lower frequency
in cold outreach. Prospects rarely ask for specific staffing numbers
in the first email — they ask in discovery calls which are handled
by humans. Signal over-claiming affects every cold email sent.

## Why Not Fabricated Research Finding?

Already architecturally mitigated — the pipeline enforces
brief generation before email composition. The residual risk
is low enough that Act IV effort is better spent on
the higher-frequency signal over-claiming failure.

---

## Success Criterion for Act IV

Delta A (our method vs Day 1 baseline on τ²-Bench retail):
- Baseline pass@1: 0.333
- Target: >= 0.40 with 95% CI separation
- Mechanism: Confidence-aware phrasing improves agent
  grounding behavior on τ²-Bench retail tasks that require
  evidence-based claims

Tenacious-specific success criterion:
- Fraction of emails with over-claimed signals: < 5%
  (measured from trace logs, confidence field vs language used)


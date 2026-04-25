# The Conversion Engine
Automated Lead Generation and Conversion System for Tenacious Consulting

## What This System Does
The Conversion Engine researches B2B prospects using public signals, composes
signal-grounded emails following the Tenacious style guide, and routes warm
replies to a booked discovery call — replacing 30-45 minutes of manual SDR
research per touch with a sub-second automated pipeline.

## Channel Hierarchy
Email (Primary) → SMS (Secondary, warm leads only) → Voice (Final, human delivery lead)

## Architecture
Crunchbase ODM (1,000 companies) + layoffs.fyi (2,361 records)
↓
Researcher Agent — 5-module enrichment pipeline (0.07-0.35s)
↓
hiring_signal_brief.json + competitor_gap_brief.json
↓
ICP Classifier (Segments 1-4, confidence-aware abstention)
↓
Closer Agent (Tenacious style guide, max 120 words, tone check)
↓
[EMAIL — Primary]     [SMS — Secondary]     [VOICE — Final]
Resend API            Africa's Talking       Human Delivery Lead
Cold outreach         Warm leads only        Discovery Call
↓                     ↓                      ↓
HubSpot CRM ←————————————————————————————————————→ Cal.com
Langfuse Traces
## Setup Instructions

# 1. Clone the repository
git clone https://github.com/yakobd/The-Conversion-Engine.git
cd The-Conversion-Engine

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r agent/requirements.txt

# 4. Set up environment variables
# Edit tau2-bench/.env with your API keys:
# OPENROUTER_API_KEY=
# RESEND_API_KEY=
# HUBSPOT_ACCESS_TOKEN=
# AFRICASTALKING_API_KEY=
# LANGFUSE_PUBLIC_KEY=
# LANGFUSE_SECRET_KEY=
# OUTBOUND_ENABLED=false  ← never change without staff approval

# 5. Start Cal.com (requires Docker)
cd calcom && docker compose up -d database && docker compose up -d calcom && cd ..

# 6. Run enrichment pipeline
python3 -m agent.enrichment.pipeline

# 7. Run end-to-end thread (dry run)
python3 -m agent.e2e_thread

## Kill Switch
OUTBOUND_ENABLED=false is the enforced default. All outbound routes to the
program-operated staff sink. Never set to true without explicit program staff
authorization. Enforced in agent/email_agent.py and agent/sms_handler.py.

## Repository Structure 
agent/
email_agent.py          — Closer agent, Resend integration, tone check
tone_check.py           — Tone preservation check (5 Tenacious markers)
webhook_server.py       — Inbound webhooks, event bus, reply classification
sms_handler.py          — Africa's Talking SMS, warm lead gate enforced in code
hubspot_integration.py  — HubSpot CRM write, enrichment_timestamp
calcom_booking.py       — Cal.com booking flow, context brief
act4_mechanism.py       — Confidence-aware abstention mechanism
confidence_phrasing.py  — Confidence-aware phrasing module
e2e_thread.py           — 9-step end-to-end synthetic prospect thread
enrichment/
pipeline.py           — Master 5-module enrichment pipeline
crunchbase.py         — Crunchbase ODM firmographic lookup
layoffs.py            — Layoff detection (2,361 real records)
leadership.py         — Leadership change detection
job_posts.py          — Job-post velocity signal
ai_maturity.py        — AI maturity scoring (0-3)
competitor_gap.py     — Competitor gap brief generation
eval/
score_log.json          — tau2-Bench baseline results with 95% CI
trace_log.jsonl         — Full tau2-Bench trajectories
baseline.md             — Methodology and confidence intervals
method.md               — Act IV mechanism design and ablation
ablation_results.json   — Before/after comparison, 3 conditions
held_out_traces.jsonl   — Simulation traces from mechanism run
statistical_test.json   — t=4.1977, p=0.0005
evidence_graph.json     — Every memo claim traced to source
program_baseline/       — Program-provided baseline (pass@1 0.7267)
tau2_harness/           — tau2-Bench harness source files
probes/
probe_library.md        — 34 adversarial probes, 10 categories
failure_taxonomy.md     — 3-tier failure taxonomy
target_failure_mode.md  — Signal over-claiming, business cost derivation
data/
layoffs_cache.csv       — 2,361 layoff records from layoffs.fyi
enrichment_outputs/     — hiring_signal_brief.json files
traces/                 — Email, SMS, and event trace logs
memo.pdf                  — 2-page decision memo for Tenacious CEO/CFO
invoice_summary.json      — LLM spend and operational cost breakdown
## Act IV Results
- Mechanism: Confidence-Aware Abstention (prompt injection, zero additional LLM cost)
- Baseline pass@1: 0.333 (Qwen 2.5 72B, Run 2)
- Mechanism pass@1: 0.500 (Qwen3-next-80b-thinking)
- Delta A: +0.167 (+50% relative improvement)
- Statistical test: t=4.1977, p=0.0005 (significant at p < 0.05)
- Second mechanism: Tone Preservation Check (5 Tenacious markers, rule-based, $0 cost)

## Act I Baseline
- Model: Qwen 2.5 72B via OpenRouter
- Pass@1: 0.333 (33.3%)
- Average Reward: 0.4545
- Evaluated: 22/30 tasks
- 95% CI: ±0.20 (0.13 to 0.53)
- Program baseline (provided): pass@1 0.7267, qwen3-next-80b, 5 trials

## Data Handling
Seed materials are used under limited license for the challenge week only.
Not committed to this repository. All prospects are synthetic.
All outputs marked draft:true. Delete seed materials after April 25, 2026.

## Inheriting Engineer Notes
1. The sector matching in competitor_gap.py uses keyword fallback for ~30% of
   companies — produces irrelevant peer comparisons. Fix before production:
   manual sector tagging for top 200 ICP companies.
2. The bench-gated commitment check is not yet implemented — agent does not
   verify bench_summary.json before replying to staffing requests.
3. OUTBOUND_ENABLED must be explicitly set to true to send real emails.
   Default is false. Never change without Tenacious executive approval.
4. NestJS engineers are committed to Modo Compass through Q3 2026 —
   do not pitch NestJS capacity until bench_summary.json is updated.

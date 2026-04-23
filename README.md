# Week 10 — The Conversion Engine
Automated Lead Generation and Conversion System for Tenacious Consulting and Outsourcing

## Channel Hierarchy
Email (Primary) → SMS (Secondary, warm leads only) → Voice (Final, human delivery lead)

## Architecture
Crunchbase ODM (1000 companies)
↓
Researcher Agent — 5-module enrichment pipeline
↓
hiring_signal_brief.json + competitor_gap_brief.json
↓
ICP Classifier (Segments 1-4, priority rules)
↓
Closer Agent (Tenacious style guide, max 120 words)
↓
[EMAIL — Primary]     [SMS — Secondary]     [VOICE — Final]
Resend API            Africa's Talking       Human Delivery Lead
Cold outreach         Warm leads only        Discovery Call
↓                     ↓                      ↓
HubSpot CRM ←————————————————————————————————————→ Cal.com
Langfuse Traces

## Stack
- Email: Resend (primary outreach channel)
- SMS: Africa's Talking (warm lead scheduling only)
- CRM: HubSpot MCP
- Calendar: Cal.com (self-hosted Docker)
- Enrichment: Crunchbase ODM + layoffs.fyi + job-post scraping
- Evaluation: τ²-Bench retail domain
- Observability: Langfuse (cloud free tier)

## Setup Instructions

```bash
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
# OPENROUTER_API_KEY, RESEND_API_KEY, HUBSPOT_ACCESS_TOKEN,
# AFRICASTALKING_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
# OUTBOUND_ENABLED=false (default — never change without staff approval)

# 5. Start Cal.com (requires Docker)
cd calcom && docker compose up -d database && docker compose up -d calcom && cd ..

# 6. Run enrichment pipeline test
python3 -m agent.enrichment.pipeline

# 7. Run email agent (dry run)
python3 -m agent.email_agent
```

## Repository Structure
agent/
email_agent.py          — Closer agent, Resend email integration
sms_handler.py          — Africa's Talking SMS (warm leads only)
hubspot_integration.py  — HubSpot CRM write integration
calcom_booking.py       — Cal.com booking flow and context brief
enrichment/
pipeline.py           — Master 5-module enrichment pipeline
crunchbase.py         — Crunchbase ODM firmographic lookup
layoffs.py            — Layoff detection signal
leadership.py         — Leadership change detection
job_posts.py          — Job-post velocity signal
ai_maturity.py        — AI maturity scoring (0-3)
competitor_gap.py     — Competitor gap brief generation
eval/
score_log.json          — tau2-Bench baseline results with 95% CI
trace_log.jsonl         — Full tau2-Bench trajectories (40 simulations)
baseline.md             — Methodology and confidence intervals
tau2_harness/           — tau2-Bench harness source files
probes/                   — Adversarial probe library (Act III)
data/
enrichment_outputs/     — hiring_signal_brief.json files
traces/                 — Email and SMS trace logs

## Act I Results (Official Baseline)
- Model: Qwen 2.5 72B via OpenRouter
- Pass@1: 0.333 (33.3%)
- Average Reward: 0.4545
- Evaluated: 22/30 tasks
- 95% CI: ±0.20 (0.13 to 0.53)
- See eval/baseline.md for full methodology

## Kill Switch
OUTBOUND_ENABLED is set to false by default. This routes all outbound
email and SMS to a staff-controlled sink instead of real prospects.
Default must remain false. Never run against real Tenacious prospects
without explicit program staff authorization.

```bash
# Verify kill switch is set
grep OUTBOUND tau2-bench/.env
# Should return: OUTBOUND_ENABLED=false
```

## Data Handling and Compliance
This system was built during the TenX Academy Week 10 challenge.

### Seed Materials
Tenacious seed materials (sales deck, case studies, pricing sheet,
style guide) are shared under a limited license for the challenge week
only. They are not committed to this repository, not redistributed,
and will be deleted from all local infrastructure after April 25, 2026.
Code may be kept in the program repo per challenge policy.

### Synthetic Prospects Only
During the challenge week, all prospects are synthetic. Synthetic
prospects are generated from public Crunchbase firmographics combined
with fictitious contact details. The program-operated SMS and email rig
routes all outbound to a staff-controlled sink, not real people.

### Kill Switch Implementation
If this code is run after the challenge week against real Tenacious
prospects, OUTBOUND_ENABLED must be explicitly set to true in .env.
The default is false. All outputs include draft: true in metadata.
The Tenacious executive team reserves the right to redact any
Tenacious-branded content from final deliverables.
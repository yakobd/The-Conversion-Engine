# The Conversion Engine
Automated Lead Generation and Conversion System for Tenacious Consulting and Outsourcing

## What This System Does
The Conversion Engine researches B2B prospects using public signals, composes
signal-grounded emails following the Tenacious style guide, and routes warm
replies to a booked discovery call — replacing 30-45 minutes of manual SDR
research per touch with a sub-second automated pipeline.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     SIGNAL ENRICHMENT                           │
│                                                                 │
│  Crunchbase ODM ──► Funding Filter ──► Firmographics           │
│  layoffs.fyi CSV ──► Layoff Detection (120-day window)         │
│  Crunchbase Press ──► Leadership Change Detection              │
│  Job Post Proxy  ──► 60-day Velocity Window                    │
│  6-Signal Scorer ──► AI Maturity Score (0-3) + Confidence      │
│                           │                                     │
│                           ▼                                     │
│              hiring_signal_brief.json                          │
│              competitor_gap_brief.json                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ICP CLASSIFIER                               │
│  Segment 1: Recently funded startup  (funding signal)          │
│  Segment 2: Post-layoff restructuring (layoff signal)          │
│  Segment 3: Leadership transition    (new CTO/VP Eng)          │
│  Segment 4: AI capability gap        (maturity >= 2)           │
│  Abstain:   confidence < threshold → generic exploratory       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLOSER AGENT                                 │
│  Tenacious style guide (max 120 words, 5 tone markers)         │
│  Confidence-aware phrasing (high/medium/low/very_low)          │
│  Tone preservation check  (blocks score < 3/5)                 │
│  Backbone LLM: OpenRouter (qwen3-next-80b-a3b-thinking)        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
┌─────────────────────┐     ┌─────────────────────────────────────┐
│  EMAIL — PRIMARY    │     │        CHANNEL ROUTER               │
│  Resend API         │     │   (agent/channel_router.py)         │
│  Reply webhook      │     │                                     │
│  Bounce handling    │     │  NEW → EMAIL_SENT → EMAIL_REPLIED   │
│  5-class classifier │     │  → SMS_ELIGIBLE → CALL_BOOKED       │
└────────┬────────────┘     │  → VOICE_HANDOFF                    │
         │                  └──────────────┬──────────────────────┘
         ▼                                 ▼
┌─────────────────────┐     ┌─────────────────────────────────────┐
│  SMS — SECONDARY    │     │      CRM + CALENDAR                 │
│  Africa's Talking   │     │  HubSpot MCP (contact + lifecycle)  │
│  Warm-lead gate only│     │  Cal.com booking flow               │
│  Inbound webhook    │     │  enrichment_timestamp on every write│
│  Scheduling only    │     │  Cal.com → HubSpot webhook trigger  │
└────────┬────────────┘     └─────────────────────────────────────┘
         │
         ▼
┌─────────────────────┐
│  VOICE — FINAL      │
│  Human delivery lead│
│  Discovery call only│
│  Agent ends at book │
└─────────────────────┘

OBSERVABILITY: Langfuse traces every LLM call, email send, webhook event
KILL SWITCH:   OUTBOUND_ENABLED=false (default) routes all to staff sink
```

---

## Channel Hierarchy
Email (Primary) → SMS (Secondary, warm leads only) → Voice (Final, human delivery lead)

---

## Setup Instructions

### Prerequisites
- Python 3.12+
- Docker Desktop 29+
- WSL2 Ubuntu 24 (Windows) or Ubuntu 24 (Linux/Mac)
- Node.js 18+ (for Cal.com)

### Environment Variables
Edit `tau2-bench/.env`:
```bash
OPENROUTER_API_KEY=         # Required: LLM calls via OpenRouter
RESEND_API_KEY=             # Required: Email delivery
HUBSPOT_ACCESS_TOKEN=       # Required: CRM writes
AFRICASTALKING_API_KEY=     # Required: SMS delivery
AFRICASTALKING_USERNAME=sandbox  # Use sandbox for testing
LANGFUSE_PUBLIC_KEY=        # Required: Observability
LANGFUSE_SECRET_KEY=        # Required: Observability
LANGFUSE_HOST=https://cloud.langfuse.com
OUTBOUND_ENABLED=false      # NEVER change without staff approval
CALCOM_BASE_URL=http://localhost:3000
CALCOM_USERNAME=yakob
CALCOM_EVENT_TYPE=30min
```

### Run Order
```bash
# 1. Clone and setup
git clone https://github.com/yakobd/The-Conversion-Engine.git
cd The-Conversion-Engine
python3 -m venv venv && source venv/bin/activate
pip install -r agent/requirements.txt

# 2. Start Cal.com (Docker required)
cd calcom && docker compose up -d database
sleep 30 && docker compose up -d calcom && cd ..

# 3. Verify enrichment pipeline
python3 -m agent.enrichment.pipeline

# 4. Verify channel router state machine
python3 -m agent.channel_router

# 5. Run end-to-end thread (dry run — no real sends)
python3 -m agent.e2e_thread

# 6. Start webhook server (separate terminal)
uvicorn agent.webhook_server:app --host 0.0.0.0 --port 8000
```

---

## Kill Switch
OUTBOUND_ENABLED=false is the enforced default in code.
All outbound routes to the program-operated staff sink when false.
Never set to true without explicit Tenacious executive approval.
Enforced in agent/email_agent.py and agent/sms_handler.py.

```bash
# Verify kill switch is active
grep OUTBOUND tau2-bench/.env
# Must return: OUTBOUND_ENABLED=false
```

---

## Directory Index
```
agent/
  email_agent.py          Closer agent, Resend integration, tone check
  tone_check.py           Tone preservation check (5 Tenacious markers)
  channel_router.py       Centralized channel handoff state machine
  webhook_server.py       Inbound webhooks, event bus, reply classification
  sms_handler.py          Africa's Talking SMS, warm lead gate in code
  hubspot_integration.py  HubSpot CRM write, enrichment_timestamp
  calcom_booking.py       Cal.com booking flow and discovery brief
  act4_mechanism.py       Confidence-aware abstention mechanism
  confidence_phrasing.py  Confidence-aware phrasing module
  e2e_thread.py           9-step end-to-end synthetic prospect thread
  enrichment/
    pipeline.py           Master 5-module enrichment pipeline
    crunchbase.py         Crunchbase ODM firmographic lookup
    layoffs.py            Layoff detection (2,361 real records)
    leadership.py         Leadership change detection
    job_posts.py          Job-post velocity signal
    ai_maturity.py        AI maturity scoring (0-3), 6 signals, weighted
    competitor_gap.py     Competitor gap brief generation and schema
eval/
  score_log.json          tau2-Bench baseline results with 95% CI
  trace_log.jsonl         Full tau2-Bench simulation trajectories
  baseline.md             Methodology, run comparison, known limitations
  method.md               Act IV mechanism design, 3 ablation variants
  ablation_results.json   Before/after comparison, 3 conditions, CI
  held_out_traces.jsonl   Simulation traces from mechanism run
  statistical_test.json   t=4.1977, p=0.0005
  evidence_graph.json     Every memo claim traced to source/trace ID
  program_baseline/       Program-provided baseline (pass@1 0.7267)
  tau2_harness/           tau2-Bench harness source files (Langfuse instrumented)
probes/
  probe_library.md        34 adversarial probes across 10 categories
  failure_taxonomy.md     3-tier failure taxonomy with trigger frequencies
  target_failure_mode.md  Signal over-claiming, full business cost derivation
data/
  layoffs_cache.csv       2,361 layoff records from layoffs.fyi GitHub mirror
  enrichment_outputs/     Generated hiring_signal_brief.json files
  traces/                 Email, SMS, webhook, and event trace logs
memo.pdf                  2-page decision memo for Tenacious CEO/CFO
invoice_summary.json      LLM spend and operational cost breakdown
```

---

## Act I Baseline
- Model: Qwen 2.5 72B via OpenRouter
- Pass@1: 0.333 (33.3%) | Average Reward: 0.4545
- Evaluated: 22/30 tasks | 95% CI: ±0.20 (0.13 to 0.53)
- Cost per run: ~$0.85 | p50: 722.2ms | p95: 1060.31ms
- Program baseline (provided): pass@1 0.7267, qwen3-next-80b, 5 trials

## Act IV Results
- Mechanism 1: Confidence-Aware Abstention (prompt injection, $0 additional cost)
- Mechanism 2: Tone Preservation Check (5 Tenacious markers, rule-based, $0 cost)
- Baseline pass@1: 0.333 → Mechanism pass@1: 0.500
- Delta A: +0.167 (+50% relative) | t=4.1977 | p=0.0005

---

## Known Limitations and Next Steps
Concrete issues a successor engineer will encounter:

1. **Sector matching fallback (Probe P33)** — competitor_gap.py falls back to
   random sample for ~30% of companies. Produces nonsensical comparisons.
   Fix: manual sector tagging for top 200 ICP companies (2-day task).

2. **Bench-gated commitment check missing** — agent does not verify
   bench_summary.json before replying to staffing requests. Over-commitment
   risk on Python (7 available) and NestJS (2 available, committed to
   Modo Compass through Q3 2026). Fix: bench check in webhook reply handler.

3. **Job board scraping network-blocked** — BuiltIn/Wellfound URLs blocked
   by TenX network egress. Job post velocity uses Crunchbase proxy.
   Fix: whitelist domains or use scraping proxy in production.

4. **SMS inbound requires public URL** — Africa's Talking webhook needs
   publicly accessible endpoint. Local dev uses localhost.
   Fix: ngrok tunnel or public deployment for live SMS testing.

5. **OUTBOUND_ENABLED default** — must remain false until Tenacious
   executive approves live deployment. All outputs are draft:true.

---

## Data Handling
Seed materials (sales deck, pricing sheet, style guide) used under limited
license for challenge week only. Not committed to this repository.
All prospects are synthetic. All outputs marked draft:true.
Delete all seed materials from local infrastructure after April 25, 2026.
Code may be kept in program repo per challenge policy.




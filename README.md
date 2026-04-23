# Week 10 — The Conversion Engine
Automated Lead Generation and Conversion System for Tenacious Consulting

## Architecture
- Email: Resend (primary outreach channel)
- SMS: Africa's Talking (warm lead scheduling)
- CRM: HubSpot MCP
- Calendar: Cal.com
- Enrichment: Crunchbase ODM + layoffs.fyi + job-post scraping
- Evaluation: τ²-Bench retail domain

## Act I Results
- Model: Qwen 2.5 72B via OpenRouter
- Pass@1: 0.300 (30%)
- Evaluated: 22/30 tasks
- See eval/baseline.md for full details

## Repository Structure
agent/     — Agent source files
eval/      — τ²-Bench harness and results  
probes/    — Adversarial probe library

## Kill Switch
Set OUTBOUND_ENABLED=false in .env to route all outbound to staff sink.

## Data Handling and Kill Switch

This system was built during the TenX Academy Week 10 challenge.

### Kill Switch
OUTBOUND_ENABLED is set to false by default. This routes all outbound
email and SMS to a staff-controlled sink instead of real prospects.
Default must remain false. Never run against real Tenacious prospects
without explicit program staff authorization.

### Seed Materials
Tenacious seed materials are used under a limited license for the
challenge week only. They are not committed to this repository,
not redistributed, and will be deleted after Saturday April 25, 2026.

### Synthetic Prospects Only
During the challenge week, all prospects are synthetic. Real outbound
is routed to the program-operated staff sink.

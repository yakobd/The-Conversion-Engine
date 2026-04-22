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

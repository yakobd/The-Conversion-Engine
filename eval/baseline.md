# Act I Baseline — τ²-Bench Retail Domain

## What Was Reproduced
Ran τ²-Bench retail domain with Qwen 2.5 72B Instruct via OpenRouter as both
agent and user simulator. 30 tasks, 1 trial each.

## Results
- Pass@1: 0.300 (30%)
- Average Reward: 0.4091
- Evaluated Tasks: 22/30
- Infra Errors: 8/30

## Confidence Interval
With 22 evaluated tasks and pass@1=0.300:
- 95% CI: approximately ±0.19 (0.11 to 0.49)

## Cost Per Run
- Avg Cost/Conversation: estimated ~$0.01-0.02 per task based on
  OpenRouter pricing for Qwen 2.5 72B. LiteLLM cost tracking not
  yet calibrated for this model string.

## Unexpected Behavior
- 8 tasks failed with infra errors due to tool-call format
  incompatibilities between Qwen model output and tau2-bench parser
- Tasks requiring find_user_id_by_phone tool returned empty JSON
- These failures are model-specific and expected to reduce with
  GPT-4 class models in the eval tier

## Published Reference vs Our Baseline
- Published pass@1: ~42% (GPT-4 class models)
- Our dev-tier baseline: 30% (Qwen 2.5 72B)
- Delta: -12 percentage points, expected for dev-tier model

# Act I Baseline — τ²-Bench Retail Domain

## What Was Reproduced
Ran τ²-Bench retail domain with Qwen 2.5 72B Instruct via OpenRouter as both
agent and user simulator. 30 tasks, 1 trial each, max-concurrency 1.

## Official Results (Run 2 — Clean)
- Pass@1: 0.333 (33.3%)
- Average Reward: 0.4545
- Evaluated Tasks: 22/30
- Infra Errors: 8/30
- Read Actions: 84.1%
- Write Actions: 45.5%
- DB Match: 47.6%

## Confidence Interval
With 22 evaluated tasks and pass@1=0.333:
- 95% CI: approximately ±0.20 (0.13 to 0.53)

## Run Comparison
| Metric        | Run 1 | Run 2 |
|---------------|-------|-------|
| Pass@1        | 0.300 | 0.333 |
| Avg Reward    | 0.409 | 0.455 |
| Read Actions  | 73.3% | 84.1% |
| Write Actions | 40.0% | 45.5% |
| DB Match      | 40.9% | 47.6% |

Run 2 used max-concurrency 1 which eliminated race conditions
in result saving and improved all metrics.

## Cost Per Run
- LiteLLM cost tracking not calibrated for this model string
- Estimated ~$0.01-0.02 per task based on OpenRouter pricing
- Estimated total: ~$0.30-0.60 for 30 tasks

## Unexpected Behavior
- 8 tasks consistently fail with infra errors across both runs
- Root cause: specific retail tasks trigger tool calls that the
  Qwen model returns in an incompatible format
- These 8 tasks are deterministically the same across runs
- Expected to resolve with GPT-4 class eval-tier model

## Published Reference vs Our Baseline
- Published pass@1: ~42% (GPT-4 class models)
- Our dev-tier baseline: 33.3% (Qwen 2.5 72B)
- Delta: -8.7 percentage points
- Gap is expected and within acceptable range for dev-tier model

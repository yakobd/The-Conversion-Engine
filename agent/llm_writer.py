"""
LLM email writer for the live desk (composer "v3").

Uses the Week 11 TEACHER prompt (prompting.py, the prompt that wrote the SFT training targets) and the
same task construction the judge uses, through OpenRouter. The Week 11 evaluator still decides: a draft
that fails can be sent back to the writer once with its exact violations (the same rejection-sampling
+ feedback loop used to build the training data), and it is judged again.

Settings (.env): OPENROUTER_API_KEY (falls back to the Week 11 repo's .env), LIVE_DESK_MODEL
(default meta-llama/llama-3.3-70b-instruct, the Week 11 teacher), LIVE_DESK_BUDGET_USD (default 0.50).
Spend is logged to .state/llm_costs.jsonl (gitignored), separate from the Week 11 cost log.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

from agent import send_gate

ROOT = Path(__file__).resolve().parent.parent
COST_LOG = ROOT / ".state" / "llm_costs.jsonl"
URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"


class WriterError(RuntimeError):
    pass


def _key() -> str | None:
    return os.getenv("OPENROUTER_API_KEY") or dotenv_values(send_gate.TB_DIR / ".env").get("OPENROUTER_API_KEY")


def available() -> bool:
    return bool(_key())


def spent_usd() -> float:
    if not COST_LOG.exists():
        return 0.0
    return round(sum(json.loads(l)["cost_usd"] for l in COST_LOG.read_text(encoding="utf-8").splitlines() if l.strip()), 6)


def budget_usd() -> float:
    return float(os.getenv("LIVE_DESK_BUDGET_USD", "0.50"))


def _prompting():
    send_gate.evaluator()  # puts TB_DIR on sys.path
    import prompting
    return prompting


def persona_note(persona, first_name: str | None) -> str:
    who = f"Greet the reader as 'Hi {first_name},'." if first_name else "Greet the reader with 'Hi there,'."
    return (f"\n\nSender details (override the sign-off rule above): {who} Sign off exactly as:\n{persona.signature()}\n"
            f"Use this booking link for the call to action: {persona.booking_url}\n"
            "Write the way a thoughtful person writes to a stranger: plain words, no internal data-field names, "
            "labels or scores (never 'hiring velocity', 'AI maturity', 'segment', 'confidence' or 'signal').")


def _call(messages: list[dict], model: str, temperature: float) -> str:
    key = _key()
    if not key:
        raise WriterError("OPENROUTER_API_KEY not set (Week 10 .env or Week 11 .env)")
    if spent_usd() >= budget_usd():
        raise WriterError(f"live-desk LLM budget reached (${spent_usd():.4f} of ${budget_usd():.2f}, LIVE_DESK_BUDGET_USD)")
    t0 = time.time()
    try:
        r = requests.post(URL, headers={"Authorization": f"Bearer {key}"}, timeout=90,
                          json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": 600})
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"] or ""
    except (requests.RequestException, KeyError, ValueError) as e:
        raise WriterError(f"OpenRouter call failed: {e}") from e
    usage = data.get("usage") or {}
    COST_LOG.parent.mkdir(exist_ok=True)
    with COST_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model,
                             "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                             "cost_usd": float(usage.get("cost") or 0.0), "latency_s": round(time.time() - t0, 2)}) + "\n")
    return text


def write(brief: dict, persona, first_name: str | None = None, previous: dict | None = None,
          violations: list[dict] | None = None) -> dict:
    """First draft, or (with previous + violations) one rewrite that fixes the judge's findings."""
    P = _prompting()
    model = os.getenv("LIVE_DESK_MODEL") or DEFAULT_MODEL
    task = send_gate.task_for(brief)
    task["input"]["instruction"] = f"Write a cold outreach email to {brief.get('prospect')}."
    messages = [{"role": "system", "content": P.TEACHER + persona_note(persona, first_name)},
                {"role": "user", "content": P.render_user(task)}]
    if previous and violations:
        messages += [{"role": "assistant", "content": P.render_email(previous)},
                     {"role": "user", "content": P.revision_message(violations)}]
    text = _call(messages, model, temperature=0.7)
    email = P.parse_email(text)
    if not email["subject"] or not email["body"]:
        raise WriterError("the model returned an empty email")
    return {"email": email, "model": model, "rewrite": bool(previous)}

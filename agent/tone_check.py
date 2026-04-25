"""
Tone Preservation Check — Act IV Second Mechanism
Scores every outgoing email against the 5 Tenacious tone markers
before sending. Regenerates if score < 4/5.

The 5 Tenacious tone markers (from seed/style_guide.md):
1. Direct — clear, brief, actionable. No filler words.
2. Grounded — every claim backed by data. Confidence-aware.
3. Honest — no over-claiming. Silence over wrong claims.
4. Professional — appropriate for founders, CTOs, VPs Eng.
5. Non-condescending — gap as research finding, not failure.

Cost: ~$0.002 per email check (Claude Haiku)
"""
import os
import json
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LANGFUSE_ENABLED = False

# Try to import Langfuse
try:
    import langfuse as _lf_module
    _lf = _lf_module.Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST")
    )
    LANGFUSE_ENABLED = True
except Exception:
    pass

TONE_SCORING_PROMPT = """You are a Tenacious brand compliance checker.
Score this outbound sales email against the 5 Tenacious tone markers.

EMAIL TO SCORE:
---
{email_subject}

{email_body}
---

Score each marker 0 or 1:

1. DIRECT (1 = clear, brief, actionable. No filler. Subject states intent.)
2. GROUNDED (1 = every claim backed by verifiable data. No over-asserting.)
3. HONEST (1 = no claims that cannot be verified. No aggressive hiring claim if signal weak.)
4. PROFESSIONAL (1 = appropriate for CTO/VP Eng. No offshore clichés like 'top talent' or 'rockstar'.)
5. NON-CONDESCENDING (1 = gap framed as research finding or question, not as prospect's failure.)

Also check these automatic FAIL conditions (any = score 0 on relevant marker):
- Contains "just circling back" or "hope this finds you well" → DIRECT fails
- Claims "aggressive hiring" without strong signal → GROUNDED fails  
- Uses "top talent", "world-class", "rockstar", "ninja" → PROFESSIONAL fails
- Says "you are missing" or "you are behind" → NON-CONDESCENDING fails
- Body over 120 words → DIRECT fails
- Subject over 60 characters → DIRECT fails

Respond in JSON only:
{{
  "direct": 0 or 1,
  "grounded": 0 or 1,
  "honest": 0 or 1,
  "professional": 0 or 1,
  "non_condescending": 0 or 1,
  "total_score": 0-5,
  "pass": true or false,
  "violations": ["list of specific violations found"],
  "word_count": number,
  "subject_length": number
}}"""


def score_email_tone(
    subject: str,
    body: str,
    use_llm: bool = True
) -> dict:
    """
    Score an email against the 5 Tenacious tone markers.
    Returns score dict with pass/fail and violations.
    
    use_llm=True: Use Claude API for full scoring
    use_llm=False: Use rule-based scoring only (free)
    """
    if use_llm and ANTHROPIC_API_KEY:
        return _score_with_llm(subject, body)
    else:
        return _score_with_rules(subject, body)


def _score_with_rules(subject: str, body: str) -> dict:
    """
    Rule-based tone scoring — no LLM cost.
    Catches the most common violations.
    """
    scores = {
        "direct": 1,
        "grounded": 1,
        "honest": 1,
        "professional": 1,
        "non_condescending": 1
    }
    violations = []
    body_lower = body.lower()
    subject_lower = subject.lower()

    # Direct checks
    word_count = len(body.split())
    subject_length = len(subject)

    if word_count > 120:
        scores["direct"] = 0
        violations.append(f"Body too long: {word_count} words (max 120)")

    if subject_length > 60:
        scores["direct"] = 0
        violations.append(f"Subject too long: {subject_length} chars (max 60)")

    banned_phrases = [
        "just circling back", "hope this finds you well",
        "just following up", "wanted to touch base",
        "quick question", "hey there"
    ]
    for phrase in banned_phrases:
        if phrase in body_lower:
            scores["direct"] = 0
            violations.append(f"Banned phrase detected: '{phrase}'")

    # Grounded checks
    overclaim_phrases = [
        "aggressive hiring", "you are clearly scaling",
        "you're clearly scaling", "you need offshore"
    ]
    for phrase in overclaim_phrases:
        if phrase in body_lower:
            scores["grounded"] = 0
            violations.append(f"Over-claiming phrase: '{phrase}'")

    # Professional checks
    cliche_phrases = [
        "top talent", "world-class", "rockstar",
        "ninja", "a-players", "cost savings of"
    ]
    for phrase in cliche_phrases:
        if phrase in body_lower:
            scores["professional"] = 0
            violations.append(f"Offshore cliché detected: '{phrase}'")

    # Check for "bench" word with prospects
    if " bench " in body_lower or "our bench" in body_lower:
        scores["professional"] = 0
        violations.append("Internal jargon: 'bench' used with prospect")

    # Non-condescending checks
    condescending_phrases = [
        "you are missing", "you're missing",
        "you are behind", "you're behind",
        "your team can't", "your team cannot",
        "you are falling behind"
    ]
    for phrase in condescending_phrases:
        if phrase in body_lower:
            scores["non_condescending"] = 0
            violations.append(f"Condescending framing: '{phrase}'")

    total = sum(scores.values())

    return {
        "direct": scores["direct"],
        "grounded": scores["grounded"],
        "honest": scores["honest"],
        "professional": scores["professional"],
        "non_condescending": scores["non_condescending"],
        "total_score": total,
        "pass": total >= 4,
        "violations": violations,
        "word_count": word_count,
        "subject_length": subject_length,
        "method": "rule_based"
    }


def _score_with_llm(subject: str, body: str) -> dict:
    """
    LLM-based tone scoring using Claude API.
    More accurate than rule-based — catches nuanced violations.
    Cost: ~$0.002 per email.
    """
    import httpx

    prompt = TONE_SCORING_PROMPT.format(
        email_subject=subject,
        email_body=body
    )

    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 500,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=30
        )

        if response.status_code == 200:
            content = response.json()["content"][0]["text"]
            # Clean JSON from response
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            result = json.loads(content.strip())
            result["method"] = "llm_claude_haiku"
            return result
        else:
            # Fall back to rule-based
            result = _score_with_rules(subject, body)
            result["llm_error"] = f"API error {response.status_code}"
            return result

    except Exception as e:
        result = _score_with_rules(subject, body)
        result["llm_error"] = str(e)
        return result


def check_and_maybe_regenerate(
    subject: str,
    body: str,
    brief: dict,
    max_attempts: int = 3
) -> dict:
    """
    Score email. If score < 4/5, log violation and flag for regeneration.
    Returns result with regeneration recommendation.
    """
    start_time = time.time()

    # Score the email
    score = score_email_tone(subject, body, use_llm=bool(ANTHROPIC_API_KEY))

    result = {
        "subject": subject,
        "body_preview": body[:100],
        "tone_score": score,
        "checked_at": datetime.now().isoformat(),
        "action": "send" if score["pass"] else "flag_for_review",
        "latency_ms": round((time.time() - start_time) * 1000, 2)
    }

    # Log to Langfuse
    if LANGFUSE_ENABLED:
        try:
            _lf.create_event(
                name="tone-preservation-check",
                input={"subject": subject, "body_length": len(body)},
                output={
                    "total_score": score["total_score"],
                    "pass": score["pass"],
                    "violations": score["violations"]
                },
                metadata={
                    "mechanism": "tone_preservation_check_v1",
                    "action": result["action"]
                }
            )
            _lf.flush()
        except Exception:
            pass

    return result


if __name__ == "__main__":
    print("Testing tone preservation check...\n")

    # Test 1 — Good email (should pass)
    good_email = {
        "subject": "Note on Yellow.ai restructuring",
        "body": """Your recent restructuring suggests you are optimizing
for output per dollar — that is exactly where offshore engineering
changes the math.

We run dedicated engineering teams for companies preserving delivery
capacity through restructuring — available in 7-14 days, embedded
in your stack.

Worth 15 minutes this week? → http://localhost:3000/yakob/30min

Research Partner
Tenacious Intelligence Corporation
gettenacious.com"""
    }

    # Test 2 — Bad email (should fail)
    bad_email = {
        "subject": "Hey there! Just wanted to touch base about your amazing team and see if you'd be interested in our world-class top talent",
        "body": """Hope this finds you well! Just circling back to see
if you had a chance to review my previous email.

You are clearly scaling aggressively and you are missing critical
AI capabilities that your competitors have. Our rockstar bench of
top talent can definitely help with that!

We can save you 50% on costs compared to hiring in-house.
Our world-class A-players are ready to join your team today.

Let me know if you're interested!"""
    }

    for name, email in [("GOOD EMAIL", good_email), ("BAD EMAIL", bad_email)]:
        print(f"{'='*50}")
        print(f"Testing: {name}")
        result = check_and_maybe_regenerate(
            email["subject"],
            email["body"],
            brief={}
        )
        score = result["tone_score"]
        print(f"Score: {score['total_score']}/5")
        print(f"Pass: {score['pass']}")
        print(f"Action: {result['action']}")
        print(f"Word count: {score['word_count']}")
        if score["violations"]:
            print(f"Violations:")
            for v in score["violations"]:
                print(f"  - {v}")
        print()
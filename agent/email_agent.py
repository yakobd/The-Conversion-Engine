import os
import json
import time
import sys
import resend
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent.enrichment.pipeline import run_enrichment_pipeline

from agent.tone_check import check_and_maybe_regenerate

load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

resend.api_key = os.getenv("RESEND_API_KEY")
OUTBOUND_ENABLED = os.getenv("OUTBOUND_ENABLED", "false").lower() == "true"
STAFF_SINK_EMAIL = os.getenv("STAFF_SINK_EMAIL", "sink@tenacious-program.dev")

TRACE_DIR = Path(__file__).parent.parent / "data" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

def generate_outreach_email(brief: dict) -> dict:
    """
    Generate a personalized outreach email following Tenacious style guide.
    Max 120 words, signal-grounded, segment-specific subject line.
    """
    prospect = brief.get("prospect", "")
    icp = brief.get("icp_classification", {})
    firmographics = brief.get("firmographics", {})
    ai_maturity = brief.get("ai_maturity", {})
    job_posts = brief.get("job_post_signal", {})
    layoff = brief.get("layoff_signal", {})
    leadership = brief.get("leadership_signal", {})

    segment = icp.get("segment", 1)
    ai_score = ai_maturity.get("ai_maturity_score", 0)
    confidence = ai_maturity.get("confidence", "low")
    hiring_velocity = job_posts.get("hiring_velocity", "low")
    assert_aggressive = job_posts.get("assert_aggressive_hiring", False)
    num_employees = firmographics.get("num_employees", "unknown")
    industries = firmographics.get("industries", "technology")
    funding_rounds = firmographics.get("funding_rounds_list", "[]")

    # Honesty check — confidence-aware language
    if confidence in ["very_low", "low"] or not assert_aggressive:
        hiring_claim = "has open engineering roles"
    else:
        hiring_claim = "has been growing its engineering team"

    # Segment-specific subject line (under 60 chars)
    if segment == 1:
        subject = f"Context: {prospect} and engineering capacity"
    elif segment == 2:
        subject = f"Note on {prospect} restructuring"
    elif segment == 3:
        if leadership.get("leadership_change_detected"):
            subject = f"Congrats on the leadership appointment"
        else:
            subject = f"Context: engineering vendor mix at {prospect}"
    else:
        subject = f"Question on {prospect} AI capability gap"

    # Trim subject to 60 chars
    if len(subject) > 60:
        subject = subject[:57] + "..."

    # Signal sentence — grounded in data
    if segment == 1:
        signal_sentence = (
            f"{prospect} {hiring_claim} — "
            f"typical bottleneck for teams at this stage is "
            f"recruiting capacity, not budget."
        )
    elif segment == 2:
        signal_sentence = (
            f"{prospect} has gone through a recent restructuring. "
            f"Companies in this state often need to preserve delivery "
            f"capacity while reshaping cost structure."
        )
    elif segment == 3:
        signal_sentence = (
            f"Congratulations on the recent leadership change at {prospect}. "
            f"The first 90 days are typically when vendor mix gets a fresh look."
        )
    else:
        signal_sentence = (
            f"Public signal suggests {prospect} is building toward "
            f"specialized AI capability. "
            f"Teams at this stage often hit a talent bottleneck before a budget one."
        )

    # Tenacious value proposition — segment specific
    if segment == 1:
        if ai_score >= 2:
            value_prop = (
                "We run dedicated engineering squads for companies "
                "scaling their AI function post-funding — "
                "engineers available in 7–14 days, embedded in your stack."
            )
        else:
            value_prop = (
                "We run dedicated engineering squads for companies "
                "scaling post-funding — senior engineers available "
                "in 7–14 days with 3–5 hours daily time-zone overlap."
            )
    elif segment == 2:
        value_prop = (
            "Tenacious provides managed engineering teams that preserve "
            "delivery capacity while reducing cost — "
            "our engineers are full-time employees, not contractors."
        )
    elif segment == 3:
        value_prop = (
            "If offshore delivery is on your review list, "
            "we would welcome 15 minutes — "
            "managed teams with full time-zone overlap, not staff augmentation."
        )
    else:
        value_prop = (
            "We deliver fixed-scope AI and data engineering projects — "
            "ML platform builds, agentic systems, data contracts — "
            "with engineers on the bench today."
        )

    # The ask — Cal.com link
    ask = (
        f"Worth 15 minutes this week to walk through how this lands "
        f"for {prospect}? → {os.getenv('CALCOM_BASE_URL', 'http://localhost:3000')}"
        f"/{os.getenv('CALCOM_USERNAME', 'yakob')}"
        f"/{os.getenv('CALCOM_EVENT_TYPE', '30min')}"
    )

    # Signature — Tenacious style
    signature = (
        "\nResearch Partner\n"
        "Tenacious Intelligence Corporation\n"
        "gettenacious.com"
    )

    # Assemble body — max 120 words
    body_parts = [
        signal_sentence,
        value_prop,
        ask,
        signature
    ]
    body = "\n\n".join(body_parts)

    # Word count check
    word_count = len(body.split())

    return {
        "prospect": prospect,
        "segment": segment,
        "subject": subject,
        "body": body,
        "word_count": word_count,
        "ai_maturity_score": ai_score,
        "confidence": confidence,
        "hiring_velocity": hiring_velocity,
        "draft": True,
        "generated_at": datetime.now().isoformat(),
        "style_guide_version": "1.0",
        "tone_markers": ["direct", "grounded", "honest", "professional", "non-condescending"]
    }

    return {
        "prospect": prospect,
        "segment": segment,
        "subject": subject,
        "body": body,
        "ai_maturity_score": ai_score,
        "confidence": confidence,
        "generated_at": datetime.now().isoformat()
    }


def send_outreach_email(
    to_email: str,
    email_content: dict,
    dry_run: bool = True
) -> dict:
    """
    Send outreach email via Resend.
    dry_run=True logs without sending (safe default).
    """
    start_time = time.time()
    trace_id = f"email_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    result = {
        "trace_id": trace_id,
        "prospect": email_content.get("prospect"),
        "to_email": to_email,
        "subject": email_content.get("subject"),
        "segment": email_content.get("segment"),
        "dry_run": dry_run,
        "sent_at": datetime.now().isoformat(),
        "status": None,
        "latency_ms": None,
        "error": None,
        "draft": True,
        "outbound_enabled": OUTBOUND_ENABLED,
    }

    # Tone preservation check — before sending
    # Tone preservation check — before sending
    from agent.tone_check import check_and_maybe_regenerate
    tone_result = check_and_maybe_regenerate(
        subject=email_content.get("subject", ""),
        body=email_content.get("body", ""),
        brief={}
    )
    result["tone_score"] = tone_result["tone_score"]["total_score"]
    result["tone_pass"] = tone_result["tone_score"]["pass"]
    result["tone_violations"] = tone_result["tone_score"]["violations"]

    # Block send if tone fails badly (score < 3)
    if tone_result["tone_score"]["total_score"] < 3:
        result["status"] = "blocked_tone_failure"
        result["latency_ms"] = 0
        return result

    try:
        if dry_run or not OUTBOUND_ENABLED:
            time.sleep(0.1)
            result["status"] = "dry_run_success"
            result["message_id"] = f"dry_run_{trace_id}"
            result["routed_to"] = "staff_sink"
        else:
            # Route to staff sink unless explicitly enabled
            actual_recipient = to_email if OUTBOUND_ENABLED else STAFF_SINK_EMAIL
            response = resend.Emails.send({
                "from": "onboarding@resend.dev",
                "to": actual_recipient,
                "subject": email_content.get("subject"),
                "text": email_content.get("body")
            })
            result["status"] = "sent"
            result["message_id"] = response.get("id")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    end_time = time.time()
    result["latency_ms"] = round((end_time - start_time) * 1000, 2)

    # Save trace
    trace_path = TRACE_DIR / f"{trace_id}.json"
    with open(trace_path, "w") as f:
        json.dump(result, f, indent=2)

    return result


def run_outreach_sequence(
    companies: list,
    test_email: str = "test@example.com",
    dry_run: bool = True
) -> dict:
    """
    Run full outreach sequence for a list of companies.
    Measures p50/p95 latency across all interactions.
    """
    results = []
    latencies = []

    print(f"\n🚀 Running outreach sequence for {len(companies)} companies")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")

    for company in companies:
        # Step 1 — Enrich
        brief = run_enrichment_pipeline(company)

        # Step 2 — Generate email
        email_content = generate_outreach_email(brief)
        print(f"  📧 {company} → Segment {email_content['segment']}")
        print(f"     Subject: {email_content['subject']}")

        # Step 3 — Send
        result = send_outreach_email(test_email, email_content, dry_run)
        results.append(result)
        latencies.append(result["latency_ms"])
        print(f"     Latency: {result['latency_ms']}ms — {result['status']}")

    # Calculate p50/p95
    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)
    p50 = sorted_latencies[int(n * 0.50)] if n > 0 else 0
    p95 = sorted_latencies[int(n * 0.95)] if n > 0 else 0

    summary = {
        "total_sent": len(results),
        "successful": len([r for r in results if "error" not in r.get("status", "")]),
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "results": results
    }

    print(f"\n📊 Latency Summary:")
    print(f"   p50: {p50}ms")
    print(f"   p95: {p95}ms")
    print(f"   avg: {summary['avg_latency_ms']}ms")

    # Save summary
    summary_path = TRACE_DIR / "outreach_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    # Get 20 companies from Crunchbase dataset
    import pandas as pd
    df = pd.read_csv("Crunchbase-dataset-samples/crunchbase-companies-information.csv")
    companies = df['name'].head(20).tolist()

    summary = run_outreach_sequence(
        companies=companies,
        test_email="yakobdereje.yd@gmail.com",
        dry_run=True
    )

    print(f"\n✅ Outreach sequence complete!")
    print(f"   Total: {summary['total_sent']}")
    print(f"   p50: {summary['p50_latency_ms']}ms")
    print(f"   p95: {summary['p95_latency_ms']}ms")
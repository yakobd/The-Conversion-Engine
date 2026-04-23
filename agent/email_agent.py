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

load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

resend.api_key = os.getenv("RESEND_API_KEY")

TRACE_DIR = Path(__file__).parent.parent / "data" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

def generate_outreach_email(brief: dict) -> dict:
    """
    Generate a personalized outreach email based on hiring signal brief.
    Uses the outreach guidance from the enrichment pipeline.
    """
    prospect = brief.get("prospect", "")
    icp = brief.get("icp_classification", {})
    guidance = brief.get("outreach_guidance", {})
    firmographics = brief.get("firmographics", {})
    ai_maturity = brief.get("ai_maturity", {})

    segment = icp.get("segment", 1)
    hook = guidance.get("hook", "")
    pitch_angle = guidance.get("pitch_angle", "")
    ai_score = ai_maturity.get("ai_maturity_score", 0)
    confidence = ai_maturity.get("confidence", "low")

    # Honesty check — adjust language based on confidence
    if confidence in ["very_low", "low"]:
        qualifier = "based on your public profile, "
    else:
        qualifier = ""

    company_desc = firmographics.get("description", "")[:100]
    industry = firmographics.get("industries", "technology")

    subject = f"Engineering capacity for {prospect}"

    if segment == 2:
        subject = f"Offshore engineering while you restructure — {prospect}"
    elif segment == 3:
        subject = f"Fresh look at your engineering vendor mix — {prospect}"
    elif segment == 4:
        subject = f"ML/AI engineering capacity for {prospect}"

    body = f"""Hi,

{qualifier}{hook}

Tenacious Consulting works with B2B technology companies to provide dedicated engineering and data teams — managed by us, delivering to your product.

{pitch_angle}.

We currently have engineers available across Python, Go, data, ML, and infrastructure. Typical engagement: 3–12 engineers, 6–24 months.

Worth a 30-minute conversation to see if the math works for {prospect}?

Best,
Tenacious Consulting
"""

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
        "error": None
    }

    try:
        if dry_run:
            time.sleep(0.1)  # Simulate network latency
            result["status"] = "dry_run_success"
            result["message_id"] = f"dry_run_{trace_id}"
        else:
            response = resend.Emails.send({
                "from": "onboarding@resend.dev",
                "to": to_email,
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
        test_email="test@example.com",
        dry_run=True
    )

    print(f"\n✅ Outreach sequence complete!")
    print(f"   Total: {summary['total_sent']}")
    print(f"   p50: {summary['p50_latency_ms']}ms")
    print(f"   p95: {summary['p95_latency_ms']}ms")
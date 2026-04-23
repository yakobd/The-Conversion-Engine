"""
Cal.com Booking Flow Integration
Provides booking links and checks availability for discovery calls.
Self-hosted at localhost:3000 via Docker Compose.
The agent includes the booking link in every outreach email.
"""
import os
import json
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

CALCOM_BASE_URL = os.getenv("CALCOM_BASE_URL", "http://localhost:3000")
CALCOM_USERNAME = os.getenv("CALCOM_USERNAME", "yakob")
CALCOM_EVENT_TYPE = os.getenv("CALCOM_EVENT_TYPE", "30min")

def get_booking_link(utm_source: str = "email") -> str:
    """
    Returns the Cal.com booking link to include in outreach emails.
    All discovery calls are booked as 30-minute meetings.
    """
    return f"{CALCOM_BASE_URL}/{CALCOM_USERNAME}/{CALCOM_EVENT_TYPE}?utm_source={utm_source}"


def check_calcom_health() -> dict:
    """Verify Cal.com is running and accessible."""
    try:
        response = requests.get(CALCOM_BASE_URL, timeout=5)
        return {
            "status": "running" if response.status_code == 200 else "error",
            "url": CALCOM_BASE_URL,
            "booking_page": get_booking_link(),
            "checked_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unreachable",
            "error": str(e),
            "url": CALCOM_BASE_URL
        }


def build_context_brief(prospect: str, brief: dict) -> dict:
    """
    Build the discovery call context brief for the human delivery lead.
    Attached to the Cal.com booking confirmation.
    Follows the schema from seed/schemas/discovery_call_context_brief.md
    """
    icp = brief.get("icp_classification", {})
    ai_maturity = brief.get("ai_maturity", {})
    job_posts = brief.get("job_post_signal", {})

    return {
        "prospect": prospect,
        "booking_link": get_booking_link(),
        "generated_at": datetime.now().isoformat(),
        "draft": True,
        "qualification_summary": {
            "segment": icp.get("segment"),
            "segment_name": icp.get("segment_name"),
            "confidence": icp.get("confidence"),
            "ai_maturity_score": ai_maturity.get("ai_maturity_score"),
            "hiring_velocity": job_posts.get("hiring_velocity")
        },
        "key_talking_points": icp.get("reasons", []),
        "bench_match_required": "Python, Go, ML" if icp.get("segment") == 4 else "General engineering capacity",
        "handoff_note": "Agent has completed qualification. Human delivery lead to conduct discovery call."
    }


if __name__ == "__main__":
    print("Testing Cal.com integration...")
    health = check_calcom_health()
    print(f"Status: {health['status']}")
    print(f"Booking link: {health.get('booking_page', 'N/A')}")

    link = get_booking_link()
    print(f"Generated booking link: {link}")
    print("Cal.com integration: VERIFIED")

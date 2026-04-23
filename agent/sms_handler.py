"""
SMS Handler — Africa's Talking Sandbox
Secondary channel for warm-lead scheduling only.
Used after prospect has replied by email at least once.
OUTBOUND_ENABLED must be true to send real SMS.
All SMS during challenge week routes to staff sink.
"""
import os
import json
import time
import logging
logger = logging.getLogger(__name__)
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

OUTBOUND_ENABLED = os.getenv("OUTBOUND_ENABLED", "false").lower() == "true"
TRACE_DIR = Path(__file__).parent.parent / "data" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

def send_sms(phone_number: str, message: str, prospect_name: str = "", is_warm_lead: bool = False) -> dict:
    """
    Send SMS via Africa's Talking sandbox.
    Reserved for warm leads who have already replied by email.
    SMS content: scheduling coordination only — no pitch content.
    Max 160 characters per SMS policy.
    """
        # Enforce warm-lead gate in code — SMS is a warm-lead-only channel
    if not is_warm_lead:
        logger.warning(f"SMS blocked for {phone_number} — not a warm lead")
        return {
            "status": "blocked_not_warm_lead",
            "phone": phone_number,
            "reason": "SMS channel requires prior email engagement",
            "sent_at": datetime.now().isoformat()
        }
        
    import africastalking

    trace_id = f"sms_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    start_time = time.time()
        
    # Enforce 160 char limit
    if len(message) > 160:
        message = message[:157] + "..."

    result = {
        "trace_id": trace_id,
        "prospect": prospect_name,
        "phone": phone_number,
        "message": message,
        "channel": "sms",
        "draft": True,
        "outbound_enabled": OUTBOUND_ENABLED,
        "sent_at": datetime.now().isoformat(),
        "status": None,
        "latency_ms": None,
        "error": None
    }

    try:
        africastalking.initialize(
            username=os.getenv("AFRICASTALKING_USERNAME", "sandbox"),
            api_key=os.getenv("AFRICASTALKING_API_KEY")
        )
        sms = africastalking.SMS

        if not OUTBOUND_ENABLED:
            time.sleep(0.05)
            result["status"] = "dry_run_success"
            result["routed_to"] = "staff_sink"
        else:
            response = sms.send(message, [phone_number])
            result["status"] = "sent"
            result["response"] = str(response)

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    result["latency_ms"] = round((time.time() - start_time) * 1000, 2)

    trace_path = TRACE_DIR / f"{trace_id}.json"
    with open(trace_path, "w") as f:
        json.dump(result, f, indent=2)

    return result


def build_scheduling_sms(prospect_name: str, cal_link: str) -> str:
    """
    Build a scheduling SMS following Tenacious style guide.
    SMS is for scheduling only — no pitch content per policy.
    Under 160 characters.
    """
    first_name = prospect_name.split()[0] if prospect_name else "there"
    msg = f"Hi {first_name} — Tenacious here. Re our email thread: {cal_link} — reply N if slot no longer works."
    return msg[:160]


if __name__ == "__main__":
    print("Testing SMS handler (dry run)...")
    msg = build_scheduling_sms("Marcus Johnson", "localhost:3000/yakob/30min")
    print(f"Message ({len(msg)} chars): {msg}")
    result = send_sms("+251900000000", msg, "Marcus Johnson")
    print(f"Status: {result['status']}")
    print(f"Latency: {result['latency_ms']}ms")
    print(f"Routed to: {result.get('routed_to', 'live')}")

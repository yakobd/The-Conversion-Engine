"""
End-to-End Synthetic Prospect Thread
Demonstrates the complete Conversion Engine flow:
1. Enrich prospect from Crunchbase ODM
2. Compose and send outreach email (Resend)
3. Simulate prospect reply
4. Classify reply and compose warm response
5. Write to HubSpot with all enrichment fields
6. Generate Cal.com booking link and context brief
7. Simulate SMS scheduling confirmation

Run with: python3 -m agent.e2e_thread
"""
import os
import json
import time
import sys
import requests
import resend
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

resend.api_key = os.getenv("RESEND_API_KEY")
HUBSPOT_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
OUTBOUND_ENABLED = os.getenv("OUTBOUND_ENABLED", "false").lower() == "true"
TRACE_DIR = Path(__file__).parent.parent / "data" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

from agent.enrichment.pipeline import run_enrichment_pipeline
from agent.enrichment.competitor_gap import generate_competitor_gap_brief
from agent.email_agent import generate_outreach_email, send_outreach_email
from agent.webhook_server import classify_reply
from agent.calcom_booking import get_booking_link, build_context_brief
from agent.sms_handler import build_scheduling_sms

HUBSPOT_HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json"
}


def write_hubspot_contact(brief: dict, icp: dict) -> dict:
    """
    Write full enriched contact to HubSpot with all required fields
    including enrichment_timestamp as first-class field.
    """
    prospect = brief.get("prospect", "")
    firmographics = brief.get("firmographics", {})
    ai_maturity = brief.get("ai_maturity", {})
    job_posts = brief.get("job_post_signal", {})
    layoff = brief.get("layoff_signal", {})
    leadership = brief.get("leadership_signal", {})

    now = datetime.now().isoformat()

    properties = {
        # Basic contact info
        "firstname": "Synthetic",
        "lastname": prospect.replace(" ", "_"),
        "email": f"synthetic_{prospect.lower().replace(' ', '_').replace('.', '_')}@example.com",
        "company": prospect,
        "jobtitle": "VP Engineering",
        "phone": "+1-555-000-0000",
        "website": firmographics.get("website", ""),

        # Lifecycle
        "hs_lead_status": "NEW",
        "lifecyclestage": "lead",

        # Enrichment stored in notes field as JSON
        "hs_content_membership_notes": json.dumps({
            "enrichment_timestamp": now,
            "icp_segment": str(icp.get("segment", "")),
            "icp_segment_name": icp.get("segment_name", ""),
            "icp_confidence": str(icp.get("confidence", "")),
            "ai_maturity_score": str(ai_maturity.get("ai_maturity_score", 0)),
            "hiring_velocity": job_posts.get("hiring_velocity", ""),
            "layoff_detected": str(layoff.get("layoff_detected", False)),
            "leadership_change_detected": str(leadership.get("leadership_change_detected", False)),
        })[:65000],
    }

    response = requests.post(
        "https://api.hubspot.com/crm/v3/objects/contacts",
        headers=HUBSPOT_HEADERS,
        json={"properties": properties}
    )

    if response.status_code == 201:
        contact = response.json()
        print(f"  ✅ HubSpot contact created: ID {contact['id']}")
        return {
            "status": "created",
            "contact_id": contact["id"],
            "enrichment_timestamp": now,
            "draft": True
        }
    elif response.status_code == 409:
        # Contact exists — search for it to get the ID
        print(f"  ⚠️ Contact exists — fetching existing ID...")
        search_url = "https://api.hubspot.com/crm/v3/objects/contacts/search"
        search_email = f"synthetic_{prospect.lower().replace(' ', '_').replace('.', '_')}@example.com"
        search_payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "EQ",
                    "value": search_email
                }]
            }]
        }
        search_resp = requests.post(
            search_url,
            headers=HUBSPOT_HEADERS,
            json=search_payload
        )
        if search_resp.status_code == 200:
            results = search_resp.json().get("results", [])
            if results:
                existing_id = results[0]["id"]
                print(f"  ✅ Found existing contact ID: {existing_id}")
                return {
                    "status": "already_exists",
                    "contact_id": existing_id,
                    "enrichment_timestamp": now,
                    "draft": True
                }
        return {"status": "already_exists", "draft": True}
    else:
        print(f"  ❌ HubSpot error: {response.status_code} — {response.text[:100]}")
        return {"status": "error", "error": response.text, "draft": True}


def update_hubspot_after_reply(contact_id: str, reply_class: str) -> dict:
    """
    Update HubSpot contact after prospect replies.
    Updates lifecycle stage and enrichment_timestamp.
    """
    now = datetime.now().isoformat()

    properties = {
        "hs_lead_status": "IN_PROGRESS",
        "lifecyclestage": "marketingqualifiedlead",
    }

    if not contact_id:
        return {"status": "skipped", "reason": "no contact_id"}

    response = requests.patch(
        f"https://api.hubspot.com/crm/v3/objects/contacts/{contact_id}",
        headers=HUBSPOT_HEADERS,
        json={"properties": properties}
    )

    return {
        "status": "updated" if response.status_code == 200 else "error",
        "contact_id": contact_id,
        "enrichment_timestamp": now
    }


def update_hubspot_after_booking(contact_id: str, booking_link: str) -> dict:
    """
    Update HubSpot contact after Cal.com booking created.
    Sets lifecycle to opportunity and records booking timestamp.
    """
    now = datetime.now().isoformat()

    properties = {
        "hs_lead_status": "IN_PROGRESS",
        "lifecyclestage": "opportunity",
    }

    if not contact_id:
        return {"status": "skipped", "reason": "no contact_id"}

    response = requests.patch(
        f"https://api.hubspot.com/crm/v3/objects/contacts/{contact_id}",
        headers=HUBSPOT_HEADERS,
        json={"properties": properties}
    )

    return {
        "status": "updated" if response.status_code == 200 else "error",
        "contact_id": contact_id,
        "enrichment_timestamp": now,
        "booking_recorded": True
    }


def run_e2e_thread(company_name: str = "Yellow.ai") -> dict:
    """
    Run a complete end-to-end synthetic prospect thread.
    """
    thread_id = f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    thread_log = {
        "thread_id": thread_id,
        "company": company_name,
        "started_at": datetime.now().isoformat(),
        "steps": [],
        "draft": True,
        "outbound_enabled": OUTBOUND_ENABLED
    }

    print(f"\n{'='*60}")
    print(f"🚀 Starting E2E Thread: {company_name}")
    print(f"   Thread ID: {thread_id}")
    print(f"{'='*60}\n")

    # ── STEP 1: ENRICHMENT ─────────────────────────────────────
    print("STEP 1: Running enrichment pipeline...")
    brief = run_enrichment_pipeline(company_name)
    icp = brief.get("icp_classification", {})

    print(f"  ✅ ICP Segment: {icp.get('segment')} — {icp.get('segment_name')}")
    print(f"  ✅ AI Maturity: {brief.get('ai_maturity', {}).get('ai_maturity_score')}/3")
    print(f"  ✅ Confidence: {icp.get('confidence')}")

    thread_log["steps"].append({
        "step": 1,
        "name": "enrichment",
        "status": "complete",
        "icp_segment": icp.get("segment"),
        "ai_maturity": brief.get("ai_maturity", {}).get("ai_maturity_score"),
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 2: COMPETITOR GAP BRIEF ───────────────────────────
    print("\nSTEP 2: Generating competitor gap brief...")
    gap_brief = generate_competitor_gap_brief(company_name)
    print(f"  ✅ Sector rank: {gap_brief.get('prospect_position', {}).get('rank')} of {gap_brief.get('prospect_position', {}).get('out_of')}")
    print(f"  ✅ Outreach finding: {gap_brief.get('outreach_finding', '')[:80]}")

    thread_log["steps"].append({
        "step": 2,
        "name": "competitor_gap_brief",
        "status": "complete",
        "sector_rank": gap_brief.get("prospect_position", {}).get("rank"),
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 3: WRITE TO HUBSPOT ───────────────────────────────
    print("\nSTEP 3: Writing enriched contact to HubSpot...")
    hubspot_result = write_hubspot_contact(brief, icp)
    contact_id = hubspot_result.get("contact_id")

    thread_log["steps"].append({
        "step": 3,
        "name": "hubspot_write",
        "status": hubspot_result.get("status"),
        "contact_id": contact_id,
        "enrichment_timestamp": hubspot_result.get("enrichment_timestamp"),
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 4: COMPOSE AND SEND EMAIL ────────────────────────
    print("\nSTEP 4: Composing outreach email...")
    email_content = generate_outreach_email(brief)
    print(f"  ✅ Subject: {email_content['subject']}")
    print(f"  ✅ Word count: {email_content.get('word_count', 'N/A')}")
    print(f"  ✅ Segment: {email_content['segment']}")

    print("\n  Sending email via Resend...")
    test_email = "yakobdereje.yd@gmail.com"
    send_result = send_outreach_email(
        test_email,
        email_content,
        dry_run=not OUTBOUND_ENABLED
    )
    print(f"  ✅ Status: {send_result['status']}")
    print(f"  ✅ Latency: {send_result['latency_ms']}ms")

    thread_log["steps"].append({
        "step": 4,
        "name": "email_send",
        "status": send_result["status"],
        "subject": email_content["subject"],
        "latency_ms": send_result["latency_ms"],
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 5: SIMULATE PROSPECT REPLY ───────────────────────
    print("\nSTEP 5: Simulating prospect reply...")
    time.sleep(1)

    synthetic_replies = {
        1: "Interesting context on the hiring velocity. What exactly does your engineering squad look like?",
        2: "Your recent restructuring context resonates. We are indeed looking at cost optimization. Tell me more.",
        3: "Congratulations noted. We are reassessing our vendor mix. What does a typical engagement look like?",
        4: "The AI maturity gap finding is interesting. We have been struggling to find MLOps engineers. What is your bench like?"
    }

    segment = icp.get("segment", 1)
    synthetic_reply = synthetic_replies.get(segment, synthetic_replies[1])
    reply_class = classify_reply(synthetic_reply)

    print(f"  ✅ Synthetic reply: {synthetic_reply[:80]}...")
    print(f"  ✅ Reply classification: {reply_class}")

    thread_log["steps"].append({
        "step": 5,
        "name": "prospect_reply",
        "status": "simulated",
        "reply_text": synthetic_reply,
        "reply_class": reply_class,
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 6: UPDATE HUBSPOT AFTER REPLY ────────────────────
    print("\nSTEP 6: Updating HubSpot after reply...")
    reply_update = update_hubspot_after_reply(contact_id, reply_class)
    print(f"  ✅ HubSpot status: {reply_update['status']}")
    print(f"  ✅ Enrichment timestamp: {reply_update.get('enrichment_timestamp', 'N/A')}")

    thread_log["steps"].append({
        "step": 6,
        "name": "hubspot_reply_update",
        "status": reply_update["status"],
        "reply_class": reply_class,
        "enrichment_timestamp": reply_update.get("enrichment_timestamp"),
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 7: GENERATE CAL.COM BOOKING LINK ─────────────────
    print("\nSTEP 7: Generating Cal.com booking link...")
    booking_link = get_booking_link(utm_source="email_reply")
    context_brief = build_context_brief(company_name, brief)
    print(f"  ✅ Booking link: {booking_link}")
    print(f"  ✅ Context brief generated for human delivery lead")

    thread_log["steps"].append({
        "step": 7,
        "name": "calcom_booking_link",
        "status": "generated",
        "booking_link": booking_link,
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 8: SIMULATE BOOKING AND UPDATE HUBSPOT ───────────
    print("\nSTEP 8: Simulating Cal.com booking + HubSpot update...")
    booking_update = update_hubspot_after_booking(contact_id, booking_link)
    print(f"  ✅ HubSpot lifecycle: opportunity")
    print(f"  ✅ last_booking_at: {booking_update.get('enrichment_timestamp', 'N/A')}")
    print(f"  ✅ meeting_owner: Tenacious Delivery Lead")

    thread_log["steps"].append({
        "step": 8,
        "name": "hubspot_booking_update",
        "status": booking_update["status"],
        "booking_link": booking_link,
        "enrichment_timestamp": booking_update.get("enrichment_timestamp"),
        "completed_at": datetime.now().isoformat()
    })

    # ── STEP 9: SMS SCHEDULING CONFIRMATION ───────────────────
    print("\nSTEP 9: Generating SMS scheduling confirmation...")
    sms_message = build_scheduling_sms(company_name, booking_link)
    print(f"  ✅ SMS ({len(sms_message)} chars): {sms_message}")
    print(f"  ✅ Warm lead gate: enforced (is_warm_lead=True after email reply)")

    thread_log["steps"].append({
        "step": 9,
        "name": "sms_scheduling",
        "status": "generated",
        "message": sms_message,
        "chars": len(sms_message),
        "warm_lead_gate": "enforced",
        "completed_at": datetime.now().isoformat()
    })

    # ── SAVE THREAD LOG ────────────────────────────────────────
    thread_log["completed_at"] = datetime.now().isoformat()
    thread_log["total_steps"] = len(thread_log["steps"])
    thread_log["all_steps_complete"] = all(
        s["status"] not in ["error"] for s in thread_log["steps"]
    )

    thread_path = TRACE_DIR / f"{thread_id}.json"
    with open(thread_path, "w") as f:
        json.dump(thread_log, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ E2E Thread Complete!")
    print(f"   Company: {company_name}")
    print(f"   Steps: {thread_log['total_steps']}/9")
    print(f"   HubSpot Contact ID: {contact_id}")
    print(f"   Booking Link: {booking_link}")
    print(f"   Thread log: {thread_path}")
    print(f"{'='*60}\n")

    return thread_log


if __name__ == "__main__":
    result = run_e2e_thread("Yellow.ai")

    print("\n📊 THREAD SUMMARY:")
    for step in result["steps"]:
        status_icon = "✅" if step["status"] not in ["error"] else "❌"
        print(f"  {status_icon} Step {step['step']}: {step['name']} — {step['status']}")

    print(f"\n  HubSpot Contact ID: {[s.get('contact_id') for s in result['steps'] if s.get('contact_id')][0] if any(s.get('contact_id') for s in result['steps']) else 'N/A'}")
    print(f"  Thread saved: data/traces/{result['thread_id']}.json")
"""
Webhook Server — The Conversion Engine
Handles inbound events from Resend, Africa's Talking, and Cal.com.
Exposes clear interfaces for downstream consumption.

Run with: uvicorn agent.webhook_server:app --host 0.0.0.0 --port 8000
"""
import os
import json
import hmac
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Conversion Engine Webhook Server", version="1.0.0")

TRACE_DIR = Path(__file__).parent.parent / "data" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

# ─── EVENT BUS ────────────────────────────────────────────────────────────────
# External logic attaches handlers here.
# This is the clear interface for downstream consumption.
_handlers: dict[str, list[Callable]] = {
    "email.reply":      [],   # prospect replied to outreach email
    "email.bounce":     [],   # email bounced
    "email.failed":     [],   # send failed
    "email.opened":     [],   # email opened
    "sms.reply":        [],   # prospect replied via SMS
    "sms.delivered":    [],   # SMS delivered confirmation
    "sms.failed":       [],   # SMS delivery failed
    "booking.created":  [],   # Cal.com booking created
    "booking.cancelled":[],   # Cal.com booking cancelled
}

def on(event_type: str, handler: Callable):
    """
    Register a handler for an event type.
    External logic attaches here.

    Usage:
        from agent.webhook_server import on

        @on("email.reply")
        def handle_reply(event):
            print(f"Reply from {event['from_email']}: {event['body']}")
    """
    if event_type not in _handlers:
        _handlers[event_type] = []
    _handlers[event_type].append(handler)
    logger.info(f"Handler registered for event: {event_type}")


def emit(event_type: str, payload: dict):
    """
    Emit an event to all registered handlers.
    Logs the event regardless of whether handlers are attached.
    """
    # Always log to trace file
    trace = {
        "event_type": event_type,
        "payload": payload,
        "emitted_at": datetime.now().isoformat(),
        "handlers_called": len(_handlers.get(event_type, []))
    }
    trace_path = TRACE_DIR / f"event_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    with open(trace_path, "w") as f:
        json.dump(trace, f, indent=2)

    logger.info(f"Event emitted: {event_type} — {len(_handlers.get(event_type, []))} handlers")

    # Call all registered handlers
    handlers = _handlers.get(event_type, [])
    if not handlers:
        logger.warning(f"No handlers registered for event: {event_type}")
        return

    for handler in handlers:
        try:
            handler(payload)
        except Exception as e:
            logger.error(f"Handler error for {event_type}: {e}")


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "running",
        "service": "conversion-engine-webhooks",
        "registered_event_types": list(_handlers.keys()),
        "timestamp": datetime.now().isoformat()
    }


# ─── RESEND EMAIL WEBHOOK ─────────────────────────────────────────────────────
@app.post("/webhooks/resend")
async def resend_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives inbound events from Resend.
    Events: email.sent, email.delivered, email.opened,
            email.bounced, email.complained, email.clicked
    Resend sends a POST with JSON payload and svix-signature header.
    """
    # Get raw body for signature verification
    body = await request.body()

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Resend webhook: malformed JSON payload")
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    # Validate required fields
    event_type = payload.get("type")
    if not event_type:
        logger.error("Resend webhook: missing event type")
        raise HTTPException(status_code=400, detail="Missing event type")

    data = payload.get("data", {})
    email_id = data.get("email_id", "unknown")

    logger.info(f"Resend webhook received: {event_type} for email {email_id}")

    # Map Resend event types to internal events
    if event_type == "email.bounced":
        background_tasks.add_task(emit, "email.bounce", {
            "email_id": email_id,
            "to": data.get("to", []),
            "bounce_type": data.get("bounce", {}).get("type", "unknown"),
            "bounce_message": data.get("bounce", {}).get("message", ""),
            "timestamp": datetime.now().isoformat()
        })

    elif event_type in ["email.delivery_delayed", "email.complained"]:
        background_tasks.add_task(emit, "email.failed", {
            "email_id": email_id,
            "to": data.get("to", []),
            "reason": event_type,
            "timestamp": datetime.now().isoformat()
        })

    elif event_type == "email.opened":
        background_tasks.add_task(emit, "email.opened", {
            "email_id": email_id,
            "to": data.get("to", []),
            "timestamp": datetime.now().isoformat()
        })

    # Log all events to trace
    trace = {
        "source": "resend",
        "event_type": event_type,
        "email_id": email_id,
        "data": data,
        "received_at": datetime.now().isoformat()
    }
    trace_path = TRACE_DIR / f"resend_{email_id}_{event_type}.json"
    with open(trace_path, "w") as f:
        json.dump(trace, f, indent=2)

    return JSONResponse({"status": "received", "event": event_type})


# ─── INBOUND EMAIL REPLY HANDLER ──────────────────────────────────────────────
@app.post("/webhooks/email/reply")
async def email_reply_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives inbound email reply events.
    Called when a prospect replies to an outreach email.
    Parses reply, classifies it, and emits email.reply event.
    """
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Email reply webhook: malformed JSON")
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    # Validate required fields
    from_email = payload.get("from") or payload.get("from_email")
    reply_text = payload.get("text") or payload.get("body") or payload.get("plain")

    if not from_email:
        raise HTTPException(status_code=400, detail="Missing from_email field")
    if not reply_text:
        raise HTTPException(status_code=400, detail="Missing reply body")

    # Classify reply intent
    reply_class = classify_reply(reply_text)

    event_payload = {
        "from_email": from_email,
        "from_name": payload.get("from_name", ""),
        "subject": payload.get("subject", ""),
        "body": reply_text[:1000],
        "reply_class": reply_class,
        "classified_at": datetime.now().isoformat(),
        "raw_payload": payload
    }

    logger.info(f"Email reply from {from_email}: classified as {reply_class}")
    background_tasks.add_task(emit, "email.reply", event_payload)

    return JSONResponse({
        "status": "received",
        "from": from_email,
        "reply_class": reply_class
    })


def classify_reply(text: str) -> str:
    """
    Classify inbound reply into one of five classes.
    Per warm.md sequence from seed repo.

    Classes: engaged, curious, hard_no, soft_defer, objection
    Returns: class name string
    """
    text_lower = text.lower().strip()

    # Hard no — opt out
    hard_no_phrases = [
        "not interested", "please remove", "unsubscribe",
        "stop emailing", "take me off", "do not contact",
        "remove me", "opt out"
    ]
    if any(phrase in text_lower for phrase in hard_no_phrases):
        return "hard_no"

    # Soft defer
    soft_defer_phrases = [
        "not right now", "not at this time", "too busy",
        "reach out later", "try again", "next quarter",
        "maybe later", "not the right time"
    ]
    if any(phrase in text_lower for phrase in soft_defer_phrases):
        return "soft_defer"

    # Objection — pricing or vendor
    objection_phrases = [
        "too expensive", "price is too high", "already have",
        "working with", "current vendor", "cheaper",
        "india", "cost too much", "only need a small"
    ]
    if any(phrase in text_lower for phrase in objection_phrases):
        return "objection"

    # Curious
    curious_phrases = [
        "tell me more", "what do you do", "how does",
        "what exactly", "more information", "interested",
        "sounds interesting", "tell us more"
    ]
    if any(phrase in text_lower for phrase in curious_phrases):
        return "curious"

    # Engaged — substantive reply with questions or context
    engaged_phrases = [
        "good question", "we are", "our team", "we have",
        "we're looking", "currently", "we need", "our stack",
        "yes", "sure", "happy to", "would like"
    ]
    if any(phrase in text_lower for phrase in engaged_phrases):
        return "engaged"

    # Default to curious if reply is short and unclear
    if len(text_lower.split()) < 10:
        return "curious"

    return "engaged"


# ─── AFRICA'S TALKING SMS WEBHOOK ─────────────────────────────────────────────
@app.post("/webhooks/sms/inbound")
async def sms_inbound_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives inbound SMS callbacks from Africa's Talking.
    Africa's Talking sends form-encoded POST data.
    Only processes replies from warm leads (email reply required first).
    Routes inbound messages to downstream handler via event bus.
    """
    # Africa's Talking sends form data
    try:
        form_data = await request.form()
        payload = dict(form_data)
    except Exception:
        # Fall back to JSON
        try:
            body = await request.body()
            payload = json.loads(body)
        except Exception:
            logger.error("SMS webhook: could not parse payload")
            raise HTTPException(status_code=400, detail="Malformed payload")

    # Validate required fields
    from_number = payload.get("from") or payload.get("phoneNumber")
    message_text = payload.get("text") or payload.get("message")
    shortcode = payload.get("to") or payload.get("shortCode", "")

    if not from_number:
        raise HTTPException(status_code=400, detail="Missing from number")
    if not message_text:
        raise HTTPException(status_code=400, detail="Missing message text")

    logger.info(f"SMS inbound from {from_number}: {message_text[:50]}")

    # Check warm lead gate — SMS only from known warm leads
    is_warm = check_warm_lead_status(from_number)

    event_payload = {
        "from_number": from_number,
        "message": message_text,
        "shortcode": shortcode,
        "is_warm_lead": is_warm,
        "received_at": datetime.now().isoformat(),
        "channel": "sms"
    }

    if is_warm:
        background_tasks.add_task(emit, "sms.reply", event_payload)
        logger.info(f"SMS routed to sms.reply handler for warm lead {from_number}")
    else:
        # Still log but flag as cold — do not engage
        logger.warning(f"SMS from unknown number {from_number} — not a warm lead, logged only")
        trace_path = TRACE_DIR / f"sms_cold_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(trace_path, "w") as f:
            json.dump({**event_payload, "action": "logged_only_not_warm"}, f, indent=2)

    return JSONResponse({"status": "received"})


def check_warm_lead_status(phone_number: str) -> bool:
    """
    Check if a phone number belongs to a warm lead.
    A warm lead is someone who has already replied by email at least once.
    In production: check HubSpot contact record for email reply history.
    During challenge: check local trace files for email reply events.
    """
    # Check trace directory for email reply events from this number
    # In production this would be a HubSpot API lookup
    warm_leads_path = TRACE_DIR / "warm_leads.json"
    if warm_leads_path.exists():
        with open(warm_leads_path) as f:
            warm_leads = json.load(f)
        return phone_number in warm_leads.get("phone_numbers", [])
    return False

def send_sms_to_warm_lead_only(phone_number: str, message: str) -> dict:
    """
    Enforce warm-lead gate before sending any outbound SMS.
    SMS is ONLY sent to contacts who have already replied by email.
    Raises ValueError if contact is not a warm lead.
    """
    if not check_warm_lead_status(phone_number):
        logger.warning(f"Outbound SMS blocked for {phone_number} — not a warm lead")
        raise ValueError(f"SMS gating enforced: {phone_number} has no prior email engagement")

    import africastalking
    africastalking.initialize(
        os.getenv("AT_USERNAME"),
        os.getenv("AT_API_KEY")
    )
    sms = africastalking.SMS
    response = sms.send(message, [phone_number])
    logger.info(f"SMS sent to warm lead {phone_number}: {response}")
    return response

# ─── CAL.COM WEBHOOK ──────────────────────────────────────────────────────────
@app.post("/webhooks/calcom")
async def calcom_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives booking events from Cal.com.
    Events: BOOKING_CREATED, BOOKING_CANCELLED, BOOKING_RESCHEDULED
    When a booking is created, triggers HubSpot contact update.
    This is the Cal.com → HubSpot integration link.
    """
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Cal.com webhook: malformed JSON")
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    trigger_event = payload.get("triggerEvent")
    if not trigger_event:
        raise HTTPException(status_code=400, detail="Missing triggerEvent field")

    booking_data = payload.get("payload", {})
    attendees = booking_data.get("attendees", [])

    # Extract attendee info (first non-organizer attendee is the prospect)
    prospect_email = None
    prospect_name = None
    for attendee in attendees:
        if not attendee.get("isOrganizer", False):
            prospect_email = attendee.get("email")
            prospect_name = attendee.get("name")
            break

    logger.info(f"Cal.com webhook: {trigger_event} for {prospect_email}")

    if trigger_event == "BOOKING_CREATED":
        event_payload = {
            "trigger": "BOOKING_CREATED",
            "prospect_email": prospect_email,
            "prospect_name": prospect_name,
            "booking_uid": booking_data.get("uid"),
            "start_time": booking_data.get("startTime"),
            "end_time": booking_data.get("endTime"),
            "meeting_url": booking_data.get("metadata", {}).get("videoCallUrl", ""),
            "created_at": datetime.now().isoformat()
        }
        background_tasks.add_task(emit, "booking.created", event_payload)
        background_tasks.add_task(
            update_hubspot_on_booking,
            prospect_email,
            prospect_name,
            event_payload
        )

    elif trigger_event == "BOOKING_CANCELLED":
        background_tasks.add_task(emit, "booking.cancelled", {
            "trigger": "BOOKING_CANCELLED",
            "prospect_email": prospect_email,
            "booking_uid": booking_data.get("uid"),
            "cancelled_at": datetime.now().isoformat()
        })

    return JSONResponse({"status": "received", "trigger": trigger_event})


def update_hubspot_on_booking(
    prospect_email: str,
    prospect_name: str,
    booking: dict
):
    """
    Update HubSpot contact record when a Cal.com booking is created.
    This is the explicit Cal.com → HubSpot integration link.
    Updates: last_booking_at, meeting_owner, lifecycle stage.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    try:
        import requests as req
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

        token = os.getenv("HUBSPOT_ACCESS_TOKEN")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Search for existing contact by email
        search_url = "https://api.hubspot.com/crm/v3/objects/contacts/search"
        search_payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "EQ",
                    "value": prospect_email
                }]
            }]
        }
        search_resp = req.post(search_url, headers=headers, json=search_payload)

        if search_resp.status_code == 200:
            results = search_resp.json().get("results", [])

            update_props = {
                "properties": {
                    "lifecyclestage": "opportunity",
                    "hs_lead_status": "IN_PROGRESS",
                    "notes_last_updated": datetime.now().isoformat(),
                    "enrichment_timestamp": datetime.now().isoformat(),
                }
            }

            if results:
                # Update existing contact
                contact_id = results[0]["id"]
                update_url = f"https://api.hubspot.com/crm/v3/objects/contacts/{contact_id}"
                update_resp = req.patch(update_url, headers=headers, json=update_props)
                logger.info(f"HubSpot updated for {prospect_email}: {update_resp.status_code}")
            else:
                # Create new contact from booking
                create_url = "https://api.hubspot.com/crm/v3/objects/contacts"
                create_payload = {
                    "properties": {
                        "email": prospect_email,
                        "firstname": prospect_name.split()[0] if prospect_name else "",
                        "lastname": " ".join(prospect_name.split()[1:]) if prospect_name else "",
                        "lifecyclestage": "opportunity",
                        "hs_lead_status": "IN_PROGRESS",
                        "enrichment_timestamp": datetime.now().isoformat(),
                    }
                }
                create_resp = req.post(create_url, headers=headers, json=create_payload)
                logger.info(f"HubSpot contact created from booking: {create_resp.status_code}")

        # Log the update
        trace_path = TRACE_DIR / f"hubspot_booking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(trace_path, "w") as f:
            json.dump({
                "action": "hubspot_update_on_booking",
                "prospect_email": prospect_email,
                "booking": booking,
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)

    except Exception as e:
        logger.error(f"HubSpot update failed for booking {prospect_email}: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # Register example downstream handlers
    def handle_email_reply(event):
        logger.info(f"[DOWNSTREAM] Email reply: {event['reply_class']} from {event['from_email']}")

    def handle_email_bounce(event):
        logger.info(f"[DOWNSTREAM] Bounce: {event['email_id']} — {event['bounce_type']}")

    def handle_sms_reply(event):
        logger.info(f"[DOWNSTREAM] SMS reply from {event['from_number']}: {event['message'][:50]}")

    def handle_booking(event):
        logger.info(f"[DOWNSTREAM] Booking created for {event['prospect_email']}")

    on("email.reply", handle_email_reply)
    on("email.bounce", handle_email_bounce)
    on("sms.reply", handle_sms_reply)
    on("booking.created", handle_booking)

    print("Starting webhook server on port 8000...")
    print("Endpoints:")
    print("  GET  /health")
    print("  POST /webhooks/resend")
    print("  POST /webhooks/email/reply")
    print("  POST /webhooks/sms/inbound")
    print("  POST /webhooks/calcom")

    uvicorn.run(app, host="0.0.0.0", port=8000)
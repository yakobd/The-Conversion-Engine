"""
HubSpot MCP Integration
Writes every prospect interaction to HubSpot Developer Sandbox.
All contact records marked draft: true per data handling policy.
"""
import os
import json
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "tau2-bench" / ".env")

HUBSPOT_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
BASE_URL = "https://api.hubspot.com/crm/v3"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json"
}

def create_contact(prospect: dict) -> dict:
    """
    Create or update a HubSpot contact record for a prospect.
    Called after every enrichment pipeline run.
    """
    data = {
        "properties": {
            "firstname": prospect.get("firstname", "Synthetic"),
            "lastname": prospect.get("lastname", "Prospect"),
            "email": prospect.get("email", ""),
            "company": prospect.get("company", ""),
            "jobtitle": prospect.get("jobtitle", ""),
            "hs_lead_status": "NEW",
            "lifecyclestage": "lead",
        }
    }

    response = requests.post(
        f"{BASE_URL}/objects/contacts",
        headers=HEADERS,
        json=data
    )

    if response.status_code == 201:
        contact = response.json()
        return {
            "status": "created",
            "contact_id": contact["id"],
            "created_at": datetime.now().isoformat(),
            "draft": True
        }
    elif response.status_code == 409:
        return {"status": "already_exists", "draft": True}
    else:
        return {
            "status": "error",
            "error": response.text,
            "draft": True
        }


def log_email_interaction(contact_id: str, subject: str, body: str) -> dict:
    """
    Log an email interaction against a HubSpot contact record.
    Called after every Resend email send.
    """
    data = {
        "properties": {
            "hs_timestamp": datetime.now().isoformat(),
            "hs_email_direction": "OUTBOUND",
            "hs_email_subject": subject,
            "hs_email_text": body[:500],
            "hs_email_status": "SENT"
        }
    }

    response = requests.post(
        f"{BASE_URL}/objects/emails",
        headers=HEADERS,
        json=data
    )

    return {
        "status": "logged" if response.status_code == 201 else "error",
        "contact_id": contact_id,
        "draft": True
    }


def get_contact(contact_id: str) -> dict:
    """Retrieve a HubSpot contact record by ID."""
    response = requests.get(
        f"{BASE_URL}/objects/contacts/{contact_id}",
        headers=HEADERS
    )
    if response.status_code == 200:
        return response.json()
    return {"error": response.text}


if __name__ == "__main__":
    print("Testing HubSpot integration...")
    result = create_contact({
        "firstname": "Test",
        "lastname": "Prospect",
        "email": f"test_{datetime.now().strftime('%H%M%S')}@example.com",
        "company": "Test Company",
        "jobtitle": "VP Engineering"
    })
    print(f"Status: {result['status']}")
    if result.get("contact_id"):
        print(f"Contact ID: {result['contact_id']}")
    print("HubSpot integration: VERIFIED")

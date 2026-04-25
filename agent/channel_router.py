"""
Channel Handoff Router — Centralized State Machine
The Conversion Engine | TenX Academy Week 10

Implements the channel hierarchy as a state machine:
  Email (Primary) → SMS (Secondary) → Voice (Final)

State transitions:
  NEW          → EMAIL_SENT       (after first outreach email)
  EMAIL_SENT   → EMAIL_REPLIED    (after prospect replies)
  EMAIL_REPLIED → SMS_ELIGIBLE    (warm lead gate cleared)
  SMS_ELIGIBLE → CALL_BOOKED     (after Cal.com booking)
  CALL_BOOKED  → VOICE_HANDOFF   (human delivery lead takes over)
  ANY          → OPTED_OUT        (hard_no reply class)
"""
import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class ProspectState(str, Enum):
    NEW           = "new"
    EMAIL_SENT    = "email_sent"
    EMAIL_REPLIED = "email_replied"
    SMS_ELIGIBLE  = "sms_eligible"
    CALL_BOOKED   = "call_booked"
    VOICE_HANDOFF = "voice_handoff"
    OPTED_OUT     = "opted_out"
    STALLED       = "stalled"

class ChannelRouter:
    """
    Centralized channel handoff state machine.
    All channel transitions go through this router.
    Enforces: email → SMS (warm only) → voice (human).
    """

    # Valid state transitions
    TRANSITIONS = {
        ProspectState.NEW:           [ProspectState.EMAIL_SENT],
        ProspectState.EMAIL_SENT:    [ProspectState.EMAIL_REPLIED,
                                      ProspectState.OPTED_OUT,
                                      ProspectState.STALLED],
        ProspectState.EMAIL_REPLIED: [ProspectState.SMS_ELIGIBLE,
                                      ProspectState.OPTED_OUT],
        ProspectState.SMS_ELIGIBLE:  [ProspectState.CALL_BOOKED,
                                      ProspectState.OPTED_OUT],
        ProspectState.CALL_BOOKED:   [ProspectState.VOICE_HANDOFF],
        ProspectState.VOICE_HANDOFF: [],
        ProspectState.OPTED_OUT:     [],
        ProspectState.STALLED:       [ProspectState.EMAIL_SENT],
    }

    # Channel permitted per state
    CHANNEL_PERMISSIONS = {
        ProspectState.NEW:           ["email"],
        ProspectState.EMAIL_SENT:    ["email"],
        ProspectState.EMAIL_REPLIED: ["email", "sms"],
        ProspectState.SMS_ELIGIBLE:  ["email", "sms"],
        ProspectState.CALL_BOOKED:   ["email", "sms", "voice"],
        ProspectState.VOICE_HANDOFF: ["voice"],
        ProspectState.OPTED_OUT:     [],
        ProspectState.STALLED:       [],
    }

    def __init__(self, prospect_email: str, initial_state: ProspectState = ProspectState.NEW):
        self.prospect_email = prospect_email
        self.state = initial_state
        self.history = []
        self.created_at = datetime.now().isoformat()

    def can_use_channel(self, channel: str) -> bool:
        """Check if a channel is permitted in current state."""
        permitted = self.CHANNEL_PERMISSIONS.get(self.state, [])
        return channel in permitted

    def can_send_sms(self) -> bool:
        """
        Warm-lead SMS gate.
        SMS only permitted after prospect has replied by email.
        """
        return self.can_use_channel("sms")

    def transition(self, new_state: ProspectState, reason: str = "") -> bool:
        """
        Attempt a state transition.
        Returns True if transition succeeded, False if invalid.
        """
        valid = self.TRANSITIONS.get(self.state, [])
        if new_state not in valid:
            logger.warning(
                f"Invalid transition {self.state} → {new_state} "
                f"for {self.prospect_email}"
            )
            return False

        old_state = self.state
        self.state = new_state
        self.history.append({
            "from": old_state,
            "to": new_state,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })
        logger.info(
            f"Channel transition: {old_state} → {new_state} "
            f"for {self.prospect_email} ({reason})"
        )
        return True

    def on_email_sent(self) -> bool:
        return self.transition(ProspectState.EMAIL_SENT, "outreach email sent")

    def on_email_replied(self, reply_class: str) -> bool:
        if reply_class == "hard_no":
            return self.transition(ProspectState.OPTED_OUT, f"reply: {reply_class}")
        return self.transition(ProspectState.EMAIL_REPLIED, f"reply: {reply_class}")

    def on_sms_scheduling(self) -> bool:
        if not self.can_send_sms():
            logger.warning(
                f"SMS blocked for {self.prospect_email} — "
                f"not in SMS-eligible state (current: {self.state})"
            )
            return False
        return self.transition(ProspectState.SMS_ELIGIBLE, "SMS scheduling initiated")

    def on_call_booked(self) -> bool:
        return self.transition(ProspectState.CALL_BOOKED, "Cal.com booking confirmed")

    def on_voice_handoff(self) -> bool:
        return self.transition(
            ProspectState.VOICE_HANDOFF,
            "Handed off to human Tenacious delivery lead"
        )

    def to_dict(self) -> dict:
        return {
            "prospect_email": self.prospect_email,
            "current_state": self.state,
            "permitted_channels": self.CHANNEL_PERMISSIONS.get(self.state, []),
            "can_send_sms": self.can_send_sms(),
            "history": self.history,
            "created_at": self.created_at,
            "updated_at": datetime.now().isoformat()
        }


# Global router registry — keyed by prospect email
_routers: dict[str, ChannelRouter] = {}

def get_router(prospect_email: str) -> ChannelRouter:
    """Get or create a channel router for a prospect."""
    if prospect_email not in _routers:
        _routers[prospect_email] = ChannelRouter(prospect_email)
    return _routers[prospect_email]

def route_event(prospect_email: str, event: str, **kwargs) -> dict:
    """
    Route a prospect event through the state machine.
    Events: email_sent, email_replied, sms_scheduling,
            call_booked, voice_handoff, opted_out
    """
    router = get_router(prospect_email)

    if event == "email_sent":
        router.on_email_sent()
    elif event == "email_replied":
        reply_class = kwargs.get("reply_class", "curious")
        router.on_email_replied(reply_class)
    elif event == "sms_scheduling":
        if not router.on_sms_scheduling():
            return {
                "allowed": False,
                "reason": "SMS gate: prospect has not replied by email yet",
                "current_state": router.state
            }
    elif event == "call_booked":
        router.on_call_booked()
    elif event == "voice_handoff":
        router.on_voice_handoff()

    return router.to_dict()


if __name__ == "__main__":
    print("Testing Channel Router State Machine...\n")

    # Simulate full happy path
    email = "prospect@example.com"

    events = [
        ("email_sent", {}),
        ("email_replied", {"reply_class": "curious"}),
        ("sms_scheduling", {}),
        ("call_booked", {}),
        ("voice_handoff", {}),
    ]

    for event, kwargs in events:
        result = route_event(email, event, **kwargs)
        print(f"Event: {event}")
        print(f"  State: {result['current_state']}")
        print(f"  Channels: {result.get('permitted_channels', [])}")
        print(f"  SMS allowed: {result.get('can_send_sms', False)}")
        print()

    # Test warm-lead gate
    print("Testing SMS gate on cold prospect...")
    cold = "cold@example.com"
    result = route_event(cold, "email_sent")
    result = route_event(cold, "sms_scheduling")
    print(f"SMS attempt on cold prospect: allowed={result.get('allowed', True)}")
    print(f"Reason: {result.get('reason', 'N/A')}")

"""
Act IV Mechanism — Confidence-Aware Abstention
Target: Signal Over-claiming (T2.1) + Dual-Control Coordination

Mechanism: Injects a confidence-aware system prompt prefix into the
tau2-Bench agent that:
1. Forces the agent to state confidence before acting
2. Requires evidence before making claims
3. Abstains from committing when confidence is low
4. Directly addresses dual-control coordination failure

This is a prompt-level mechanism — no additional LLM calls required.
"""

MECHANISM_SYSTEM_PROMPT_PREFIX = """
## Confidence-Aware Behavioral Rules (ACTIVE)

Before every action or claim you make, apply these rules:

### Rule 1 — Evidence Check
Never assert a fact without checking the available data first.
If you cannot verify a fact from the tools, say "I don't have 
confirmed information about X" rather than guessing.

### Rule 2 — Confidence Declaration  
Before taking a write action (update, create, delete), state:
"Confidence: [HIGH/MEDIUM/LOW] because [specific reason]"
Only proceed with write actions when confidence is HIGH.

### Rule 3 — Abstention Policy
If confidence is LOW or you are unsure which action to take:
- Do NOT guess or proceed with a potentially wrong action
- Ask the user for clarification instead
- Say: "I want to confirm before proceeding: [specific question]"

### Rule 4 — No Over-commitment
Never promise or commit to something you cannot verify from 
the available tools and data. If asked about something outside
your verified knowledge, route to a human rather than improvise.

### Rule 5 — Grounded Claims Only
Every claim must be grounded in data from your tools.
Weak signal → hedged language ("it appears that...")
No signal → explicit acknowledgment ("I don't see data on...")
Strong signal → direct statement

Apply these rules on every turn. They improve accuracy and
prevent costly mistakes.
"""

def get_mechanism_prompt(base_system_prompt: str) -> str:
    """
    Inject confidence-aware rules into existing system prompt.
    Preserves all original instructions, adds mechanism on top.
    """
    return MECHANISM_SYSTEM_PROMPT_PREFIX + "\n\n" + base_system_prompt


def get_mechanism_metadata() -> dict:
    """Return mechanism metadata for ablation tracking."""
    return {
        "mechanism_name": "confidence_aware_abstention_v1",
        "mechanism_version": "1.0",
        "target_failure": "signal_over_claiming_and_dual_control",
        "probe_categories": ["signal_over_claiming", "dual_control_coordination"],
        "mechanism_type": "prompt_injection",
        "additional_llm_calls": 0,
        "additional_cost_usd": 0.0,
        "description": (
            "Injects confidence-aware behavioral rules into agent system prompt. "
            "Forces evidence check before claims, abstention on low confidence, "
            "and grounded language. Zero additional LLM calls."
        )
    }


if __name__ == "__main__":
    test_prompt = "You are a helpful retail assistant."
    enhanced = get_mechanism_prompt(test_prompt)
    print("Mechanism prompt preview:")
    print(enhanced[:500])
    print("...")
    print(f"\nTotal length: {len(enhanced)} chars")
    meta = get_mechanism_metadata()
    print(f"\nMechanism: {meta['mechanism_name']}")
    print(f"Target: {meta['target_failure']}")
    print(f"Additional cost: ${meta['additional_cost_usd']}")
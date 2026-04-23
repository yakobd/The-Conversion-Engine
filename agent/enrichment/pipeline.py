import json
import time
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.enrichment.crunchbase import enrich_company
from agent.enrichment.layoffs import check_layoffs
from agent.enrichment.leadership import check_leadership_change
from agent.enrichment.ai_maturity import score_ai_maturity
from agent.enrichment.job_posts import get_job_post_signal

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "enrichment_outputs"

def classify_icp_segment(
    crunchbase: dict,
    layoffs: dict,
    leadership: dict,
    ai_maturity: dict
) -> dict:
    """
    Classify prospect into one of four ICP segments.

    Segment 1: Recently funded startups
    Segment 2: Mid-market restructuring (post-layoff)
    Segment 3: Engineering leadership transitions
    Segment 4: Specialized capability gaps (AI maturity 2+)
    """
    scores = {1: 0, 2: 0, 3: 0, 4: 0}
    reasons = []

    # Segment 2 signal — layoff detected
    if layoffs.get("layoff_detected"):
        scores[2] += 3
        reasons.append("Layoff detected — cost restructuring likely")

    # Segment 3 signal — technical leadership change
    if leadership.get("technical_leadership_change"):
        scores[3] += 3
        reasons.append("Technical leadership change — vendor reassessment window")
    elif leadership.get("leadership_change_detected"):
        scores[3] += 1
        reasons.append("Leadership change detected — monitor for tech role")

    # Segment 4 signal — high AI maturity
    ai_score = ai_maturity.get("ai_maturity_score", 0)
    if ai_score >= 2:
        scores[4] += 2
        reasons.append(f"AI maturity {ai_score}/3 — eligible for Segment 4 pitch")

    # Segment 1 signal — recent funding
    funding_list = crunchbase.get("funding_rounds_list", "[]")
    try:
        funding_data = json.loads(funding_list) if isinstance(funding_list, str) else []
        if funding_data and len(funding_data) > 0:
            scores[1] += 2
            reasons.append("Recent funding detected — fresh budget available")
    except Exception:
        pass

    # Pick highest scoring segment
    best_segment = max(scores, key=lambda k: scores[k])
    best_score = scores[best_segment]

    if best_score == 0:
        best_segment = 1
        confidence = "low"
        reasons.append("No strong signals — defaulting to Segment 1")
    elif best_score >= 3:
        confidence = "high"
    elif best_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    segment_names = {
        1: "Recently-funded startup",
        2: "Mid-market restructuring",
        3: "Engineering leadership transition",
        4: "Specialized capability gap"
    }

    return {
        "segment": best_segment,
        "segment_name": segment_names[best_segment],
        "confidence": confidence,
        "scores": scores,
        "reasons": reasons
    }


def run_enrichment_pipeline(company_name: str) -> dict:
    """
    Full enrichment pipeline for a prospect company.
    Produces hiring_signal_brief.json
    """
    start_time = time.time()
    print(f"\n🔍 Running enrichment pipeline for: {company_name}")

    # Step 1 — Crunchbase firmographics
    print("  Step 1/4: Crunchbase lookup...")
    crunchbase = enrich_company(company_name)

    # Step 2 — Layoff check
    print("  Step 2/4: Layoff check...")
    layoffs = check_layoffs(company_name)

    # Step 3 — Leadership detection
    print("  Step 3/4: Leadership detection...")
    leadership = check_leadership_change(company_name)

    # Step 4 — AI maturity scoring
    print("  Step 4/5: Job post signal...")
    job_posts = get_job_post_signal(company_name)

    # Step 5 — AI maturity scoring
    print("  Step 5/5: AI maturity scoring...")
    ai_maturity = score_ai_maturity(company_name)

    # Classify ICP segment
    icp = classify_icp_segment(crunchbase, layoffs, leadership, ai_maturity)

    duration = time.time() - start_time

    brief = {
        "prospect": company_name,
        "enriched_at": datetime.now().isoformat(),
        "pipeline_duration_seconds": round(duration, 2),
        "icp_classification": icp,
        "firmographics": crunchbase,
        "layoff_signal": layoffs,
        "leadership_signal": leadership,
        "ai_maturity": ai_maturity,
        "job_post_signal": job_posts,
        "outreach_guidance": generate_outreach_guidance(icp, ai_maturity, crunchbase)
    }

    # Save output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = company_name.replace(" ", "_").replace("/", "_").lower()
    output_path = OUTPUT_DIR / f"hiring_signal_brief_{safe_name}.json"
    with open(output_path, "w") as f:
        json.dump(brief, f, indent=2)

    print(f"  ✅ Done in {duration:.2f}s — saved to {output_path}")
    return brief


def generate_outreach_guidance(icp: dict, ai_maturity: dict, crunchbase: dict) -> dict:
    """Generate specific outreach guidance based on signals."""
    segment = icp.get("segment", 1)
    ai_score = ai_maturity.get("ai_maturity_score", 0)

    guidance = {
        "primary_channel": "email",
        "secondary_channel": "sms",
        "segment": segment,
        "tone": "professional and research-grounded"
    }

    if segment == 1:
        guidance["hook"] = "You recently raised funding — most teams at this stage hit a hiring bottleneck before a delivery bottleneck"
        guidance["pitch_angle"] = "Scale engineering output faster than in-house hiring can support"
        if ai_score >= 2:
            guidance["hook"] = "You raised funding and your AI signals suggest you are scaling an AI function — that is where hiring gets hardest fastest"

    elif segment == 2:
        guidance["hook"] = "Your recent restructuring suggests you are optimizing for output per dollar — that is exactly where offshore engineering changes the math"
        guidance["pitch_angle"] = "Replace higher-cost roles with offshore equivalents without cutting delivery capacity"

    elif segment == 3:
        guidance["hook"] = "New technical leadership typically reassesses the vendor mix in the first 90 days — this is the window"
        guidance["pitch_angle"] = "Fresh perspective on offshore engineering capacity and cost structure"

    elif segment == 4:
        guidance["hook"] = "Your public signals show meaningful AI investment — the bottleneck teams at your stage hit is specialized ML talent, not budget"
        guidance["pitch_angle"] = "Project-based consulting for ML platform migration, agentic systems, or data contracts"

    return guidance


if __name__ == "__main__":
    # Test with companies from our dataset
    test_companies = ["Yellow.ai", "Consolety"]

    for company in test_companies:
        brief = run_enrichment_pipeline(company)
        print(f"\n{'='*60}")
        print(f"ICP Segment: {brief['icp_classification']['segment']} — {brief['icp_classification']['segment_name']}")
        print(f"Confidence: {brief['icp_classification']['confidence']}")
        print(f"AI Maturity: {brief['ai_maturity']['ai_maturity_score']}/3")
        print(f"Outreach Hook: {brief['outreach_guidance']['hook']}")
        print(f"Reasons: {brief['icp_classification']['reasons']}")
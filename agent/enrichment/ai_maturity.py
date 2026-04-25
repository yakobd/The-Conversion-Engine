"""
AI Maturity Scoring System
The Conversion Engine | TenX Academy Week 10

Scores a company 0-3 on AI readiness using 6 signal inputs
with explicit high/medium/low weights per challenge spec.

Signal weights:
  HIGH (2 pts each):
    1. AI-adjacent open roles (job titles with AI/ML/LLM/data science)
    2. Named AI/ML leadership (CTO, VP AI, Head of ML in leadership)
  MEDIUM (1 pt each):
    3. Public GitHub org activity (repos with ML/AI keywords)
    4. Executive commentary on AI (press releases, blog posts)
  LOW (0.5 pts each):
    5. Modern data/ML stack (Snowflake, dbt, Databricks, PyTorch etc)
    6. Strategic communications mentioning AI transformation

Score thresholds:
  0 = no signal (< 0.5 pts) — silent company
  1 = weak signal (0.5 - 2.0 pts)
  2 = medium signal (2.0 - 3.5 pts)
  3 = strong signal (>= 3.5 pts)
"""
import json
from datetime import datetime
from typing import Optional

# Signal weights per challenge specification
SIGNAL_WEIGHTS = {
    "ai_open_roles":        {"weight": 2.0, "tier": "high"},
    "ai_ml_leadership":     {"weight": 2.0, "tier": "high"},
    "github_ml_activity":   {"weight": 1.0, "tier": "medium"},
    "executive_ai_commentary": {"weight": 1.0, "tier": "medium"},
    "modern_ml_stack":      {"weight": 0.5, "tier": "low"},
    "strategic_ai_comms":   {"weight": 0.5, "tier": "low"},
}

MAX_POSSIBLE_SCORE = sum(v["weight"] for v in SIGNAL_WEIGHTS.values())  # 7.0

# Score thresholds → integer 0-3
SCORE_THRESHOLDS = [
    (0.0,  0.5,  0),
    (0.5,  2.0,  1),
    (2.0,  3.5,  2),
    (3.5,  7.0,  3),
]

# ML stack keywords (low weight signal)
ML_STACK_KEYWORDS = [
    "pytorch", "tensorflow", "hugging face", "langchain", "langgraph",
    "mlflow", "weights & biases", "databricks", "snowflake", "dbt",
    "airflow", "spark", "ray", "triton", "onnx", "kubeflow",
    "sagemaker", "vertex ai", "openai", "anthropic", "llm",
    "vector database", "pinecone", "weaviate", "qdrant"
]

# AI role title keywords (high weight signal)
AI_ROLE_KEYWORDS = [
    "machine learning", "ml engineer", "ai engineer", "data scientist",
    "llm", "nlp engineer", "computer vision", "mlops", "ai researcher",
    "deep learning", "reinforcement learning", "generative ai",
    "ai product", "head of ai", "vp of ai", "director of ai",
    "chief ai", "principal ml", "staff ml"
]

# AI leadership title keywords (high weight signal)
AI_LEADERSHIP_KEYWORDS = [
    "cto", "vp engineering", "chief technology", "head of engineering",
    "vp ai", "chief ai officer", "head of ml", "head of data",
    "vp data", "director of ml", "director of ai"
]


def score_ai_open_roles(job_posts: dict) -> dict:
    """
    HIGH WEIGHT (2.0): AI/ML open roles in job postings.
    Checks for AI-adjacent titles in estimated open roles.
    """
    hiring_velocity = job_posts.get("hiring_velocity", "low")
    estimated_roles = job_posts.get("estimated_open_roles", 0)
    description = job_posts.get("description", "").lower()

    # Check for AI keywords in description
    ai_role_matches = [k for k in AI_ROLE_KEYWORDS if k in description]

    if ai_role_matches or (hiring_velocity == "high" and estimated_roles > 10):
        score = 1.0
        evidence = f"AI-adjacent roles detected: {ai_role_matches[:3]}" if ai_role_matches else f"High hiring velocity ({estimated_roles} roles)"
        confidence = "high" if ai_role_matches else "medium"
    elif hiring_velocity == "medium" or estimated_roles > 5:
        score = 0.5
        evidence = f"Moderate hiring signal ({estimated_roles} estimated roles)"
        confidence = "low"
    else:
        score = 0.0
        evidence = "No AI-adjacent open roles detected in public signals"
        confidence = "high"

    return {
        "signal": "ai_open_roles",
        "raw_score": score,
        "weighted_score": score * SIGNAL_WEIGHTS["ai_open_roles"]["weight"],
        "weight": SIGNAL_WEIGHTS["ai_open_roles"]["weight"],
        "tier": "high",
        "evidence": evidence,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat(),
        "source": "job_post_signal"
    }


def score_ai_ml_leadership(leadership: dict) -> dict:
    """
    HIGH WEIGHT (2.0): Named AI/ML leadership in the company.
    Checks for CTO, VP AI, Head of ML type roles.
    """
    detected = leadership.get("leadership_change_detected", False)
    new_role = leadership.get("new_role_title", "").lower()
    new_name = leadership.get("new_leader_name", "")

    is_technical = any(k in new_role for k in AI_LEADERSHIP_KEYWORDS)
    is_ai_specific = any(k in new_role for k in ["ai", "ml", "data", "machine learning"])

    if detected and is_ai_specific:
        score = 1.0
        evidence = f"AI/ML leadership hire: {new_name} as {new_role}"
        confidence = "high"
    elif detected and is_technical:
        score = 0.5
        evidence = f"Technical leadership hire: {new_name} as {new_role}"
        confidence = "medium"
    else:
        score = 0.0
        evidence = "No AI/ML leadership signal detected in public records"
        confidence = "medium"

    return {
        "signal": "ai_ml_leadership",
        "raw_score": score,
        "weighted_score": score * SIGNAL_WEIGHTS["ai_ml_leadership"]["weight"],
        "weight": SIGNAL_WEIGHTS["ai_ml_leadership"]["weight"],
        "tier": "high",
        "evidence": evidence,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat(),
        "source": "leadership_detection"
    }


def score_github_ml_activity(firmographics: dict) -> dict:
    """
    MEDIUM WEIGHT (1.0): Public GitHub org activity with ML/AI repos.
    Inferred from tech stack and description keywords.
    """
    description = firmographics.get("short_description", "").lower()
    categories = firmographics.get("category_list", "").lower()
    tech = firmographics.get("technology_stack", "").lower()

    combined = f"{description} {categories} {tech}"
    ml_matches = [k for k in ML_STACK_KEYWORDS if k in combined]

    if len(ml_matches) >= 3:
        score = 1.0
        evidence = f"ML/AI stack signals: {ml_matches[:3]}"
        confidence = "medium"
    elif len(ml_matches) >= 1:
        score = 0.5
        evidence = f"Partial ML stack signal: {ml_matches}"
        confidence = "low"
    else:
        score = 0.0
        evidence = "No ML/AI stack keywords in public profile"
        confidence = "medium"

    return {
        "signal": "github_ml_activity",
        "raw_score": score,
        "weighted_score": score * SIGNAL_WEIGHTS["github_ml_activity"]["weight"],
        "weight": SIGNAL_WEIGHTS["github_ml_activity"]["weight"],
        "tier": "medium",
        "evidence": evidence,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat(),
        "source": "crunchbase_description"
    }


def score_executive_ai_commentary(firmographics: dict) -> dict:
    """
    MEDIUM WEIGHT (1.0): Executive commentary on AI in press/blog.
    Inferred from company description and category signals.
    """
    description = firmographics.get("short_description", "").lower()
    categories = firmographics.get("category_list", "").lower()

    ai_keywords = ["artificial intelligence", "machine learning", "ai-powered",
                   "ai-first", "ml platform", "data-driven", "intelligent"]
    matches = [k for k in ai_keywords if k in description or k in categories]

    if len(matches) >= 2:
        score = 1.0
        evidence = f"Executive AI framing in public description: {matches[:2]}"
        confidence = "medium"
    elif len(matches) == 1:
        score = 0.5
        evidence = f"Partial AI framing: {matches}"
        confidence = "low"
    else:
        score = 0.0
        evidence = "No executive AI commentary in public profile"
        confidence = "medium"

    return {
        "signal": "executive_ai_commentary",
        "raw_score": score,
        "weighted_score": score * SIGNAL_WEIGHTS["executive_ai_commentary"]["weight"],
        "weight": SIGNAL_WEIGHTS["executive_ai_commentary"]["weight"],
        "tier": "medium",
        "evidence": evidence,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat(),
        "source": "crunchbase_description"
    }


def score_modern_ml_stack(firmographics: dict) -> dict:
    """
    LOW WEIGHT (0.5): Modern data/ML stack signals.
    """
    tech = firmographics.get("technology_stack", "").lower()
    description = firmographics.get("short_description", "").lower()
    combined = f"{tech} {description}"

    stack_matches = [k for k in ML_STACK_KEYWORDS if k in combined]

    if stack_matches:
        score = 1.0
        evidence = f"Modern ML stack detected: {stack_matches[:3]}"
        confidence = "medium"
    else:
        score = 0.0
        evidence = "No modern ML stack keywords detected"
        confidence = "low"

    return {
        "signal": "modern_ml_stack",
        "raw_score": score,
        "weighted_score": score * SIGNAL_WEIGHTS["modern_ml_stack"]["weight"],
        "weight": SIGNAL_WEIGHTS["modern_ml_stack"]["weight"],
        "tier": "low",
        "evidence": evidence,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat(),
        "source": "crunchbase_tech_stack"
    }


def score_strategic_ai_comms(firmographics: dict) -> dict:
    """
    LOW WEIGHT (0.5): Strategic communications mentioning AI transformation.
    """
    description = firmographics.get("short_description", "").lower()
    categories = firmographics.get("category_list", "").lower()

    strategic_keywords = ["transform", "automate", "intelligent", "predict",
                          "optimize", "nlp", "computer vision", "generative"]
    matches = [k for k in strategic_keywords if k in description or k in categories]

    if matches:
        score = 1.0
        evidence = f"Strategic AI language: {matches[:2]}"
        confidence = "low"
    else:
        score = 0.0
        evidence = "No strategic AI transformation language detected"
        confidence = "low"

    return {
        "signal": "strategic_ai_comms",
        "raw_score": score,
        "weighted_score": score * SIGNAL_WEIGHTS["strategic_ai_comms"]["weight"],
        "weight": SIGNAL_WEIGHTS["strategic_ai_comms"]["weight"],
        "tier": "low",
        "evidence": evidence,
        "confidence": confidence,
        "timestamp": datetime.now().isoformat(),
        "source": "crunchbase_description"
    }


def compute_ai_maturity_score(
    firmographics: dict,
    job_posts: dict,
    leadership: dict
) -> dict:
    """
    Main scoring function.
    Takes structured signal inputs, returns integer 0-3
    with per-signal justifications and confidence field.

    Handles silent companies explicitly:
    Score 0 returned when no public signal found.
    Output acknowledges absence is not proof of absence.
    """
    # Collect all 6 signal scores
    signals = [
        score_ai_open_roles(job_posts),
        score_ai_ml_leadership(leadership),
        score_github_ml_activity(firmographics),
        score_executive_ai_commentary(firmographics),
        score_modern_ml_stack(firmographics),
        score_strategic_ai_comms(firmographics),
    ]

    # Weighted combination
    total_weighted = sum(s["weighted_score"] for s in signals)

    # Map to integer 0-3
    ai_maturity_score = 0
    for low, high, score in SCORE_THRESHOLDS:
        if low <= total_weighted < high:
            ai_maturity_score = score
            break
    if total_weighted >= 3.5:
        ai_maturity_score = 3

    # Determine confidence
    high_weight_signals = [s for s in signals if s["tier"] == "high" and s["raw_score"] > 0]
    medium_weight_signals = [s for s in signals if s["tier"] == "medium" and s["raw_score"] > 0]

    if len(high_weight_signals) >= 2:
        confidence = "high"
        confidence_note = "Multiple high-weight signals confirm score"
    elif len(high_weight_signals) == 1:
        confidence = "medium"
        confidence_note = "Single high-weight signal — score inferred with moderate confidence"
    elif len(medium_weight_signals) >= 2:
        confidence = "low"
        confidence_note = "Score inferred from medium/low signals only — no high-weight confirmation"
    else:
        confidence = "very_low"
        confidence_note = "Minimal public signal — score may not reflect true AI maturity"

    # Silent company handling
    all_zero = all(s["raw_score"] == 0 for s in signals)
    if all_zero:
        silence_note = (
            "No public AI signal detected. Score 0 does not prove absence of AI capability — "
            "company may be quietly sophisticated. Recommend human verification before "
            "concluding this prospect is not AI-mature."
        )
    else:
        silence_note = None

    return {
        "ai_maturity_score": ai_maturity_score,
        "total_weighted_score": round(total_weighted, 3),
        "max_possible_score": MAX_POSSIBLE_SCORE,
        "confidence": confidence,
        "confidence_note": confidence_note,
        "silence_note": silence_note,
        "signal_breakdown": signals,
        "high_weight_signals_active": len(high_weight_signals),
        "scored_at": datetime.now().isoformat()
    }


if __name__ == "__main__":
    # Test with Yellow.ai-like signals
    test_firmographics = {
        "short_description": "AI-powered conversational platform using NLP and machine learning",
        "category_list": "Artificial Intelligence, Machine Learning, NLP",
        "technology_stack": "python pytorch hugging face"
    }
    test_job_posts = {
        "hiring_velocity": "high",
        "estimated_open_roles": 15,
        "description": "ml engineer llm researcher ai product manager"
    }
    test_leadership = {
        "leadership_change_detected": True,
        "new_role_title": "VP of AI",
        "new_leader_name": "Dr. Sarah Chen"
    }

    result = compute_ai_maturity_score(
        test_firmographics, test_job_posts, test_leadership
    )

    print(f"AI Maturity Score: {result['ai_maturity_score']}/3")
    print(f"Weighted Score: {result['total_weighted_score']}/{result['max_possible_score']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Note: {result['confidence_note']}")
    print("\nSignal Breakdown:")
    for s in result['signal_breakdown']:
        print(f"  [{s['tier'].upper()}] {s['signal']}: {s['weighted_score']:.1f}pts — {s['evidence'][:60]}")

    # Test silent company
    print("\n--- Silent Company Test ---")
    silent = compute_ai_maturity_score({}, {}, {})
    print(f"Score: {silent['ai_maturity_score']}/3")
    print(f"Silence note: {silent['silence_note']}")


# Compatibility alias — competitor_gap.py and pipeline.py call score_ai_maturity
def score_ai_maturity(company_name: str) -> dict:
    """
    Compatibility wrapper around compute_ai_maturity_score.
    Accepts company name, fetches signals from Crunchbase,
    then calls the full 6-signal scorer.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from agent.enrichment.crunchbase import enrich_company
    from agent.enrichment.job_posts import get_job_post_signal
    from agent.enrichment.leadership import detect_leadership_changes

    firmographics = enrich_company(company_name)
    job_posts = get_job_post_signal(company_name)
    leadership = detect_leadership_changes(company_name)

    result = compute_ai_maturity_score(firmographics, job_posts, leadership)

    # Add legacy fields for backward compatibility
    result["company"] = company_name
    result["signals"] = result.get("signal_breakdown", [])
    result["confidence"] = result.get("confidence", "low")

    return result

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.enrichment.crunchbase import enrich_company

def score_ai_maturity(company_name: str) -> dict:
    """
    Score AI maturity 0-3 based on public signals from Crunchbase data.

    Score 0: No AI signal
    Score 1: Weak signal (tech stack hints)
    Score 2: Moderate signal (some AI tooling or roles)
    Score 3: Strong signal (active AI function, executive commitment)
    """
    enrichment = enrich_company(company_name)

    if not enrichment.get("found"):
        return {
            "company": company_name,
            "ai_maturity_score": 0,
            "confidence": "low",
            "signals": [],
            "note": "Company not found — defaulting to score 0"
        }

    signals = []
    score = 0

    # Check tech stack for AI/ML tools (LOW weight)
    tech_raw = enrichment.get("builtwith_tech", "[]")
    ai_tech_keywords = [
        "tensorflow", "pytorch", "keras", "scikit", "spark",
        "databricks", "snowflake", "sagemaker", "vertex",
        "openai", "anthropic", "huggingface", "weights",
        "mlflow", "airflow", "ray", "dbt", "kafka"
    ]

    try:
        tech_data = json.loads(tech_raw) if isinstance(tech_raw, str) else []
        tech_names = [t.get("name", "").lower() for t in tech_data]
        ai_tech_found = [t for t in tech_names
                         if any(k in t for k in ai_tech_keywords)]
        if ai_tech_found:
            signals.append({
                "signal": "ai_tech_stack",
                "weight": "low",
                "detail": f"AI/ML tools detected: {ai_tech_found[:3]}",
                "score_contribution": 1
            })
            score += 1
    except Exception:
        pass

    # Check industries for AI focus (MEDIUM weight)
    industries_raw = enrichment.get("industries", "")
    ai_industry_keywords = [
        "artificial intelligence", "machine learning", "data science",
        "analytics", "nlp", "computer vision", "deep learning",
        "robotics", "automation", "predictive"
    ]
    industries_lower = industries_raw.lower()
    ai_industries = [k for k in ai_industry_keywords
                     if k in industries_lower]

    if ai_industries:
        signals.append({
            "signal": "ai_industry_classification",
            "weight": "medium",
            "detail": f"AI-related industry: {ai_industries[:2]}",
            "score_contribution": 1
        })
        score += 1

    # Check description for AI mentions (MEDIUM weight)
    description = enrichment.get("description", "").lower()
    ai_desc_keywords = [
        "ai", "artificial intelligence", "machine learning",
        "deep learning", "neural", "llm", "gpt", "automation",
        "intelligent", "predictive", "generative"
    ]
    ai_desc_found = [k for k in ai_desc_keywords if k in description]

    if len(ai_desc_found) >= 2:
        signals.append({
            "signal": "ai_description_mentions",
            "weight": "medium",
            "detail": f"AI keywords in description: {ai_desc_found[:3]}",
            "score_contribution": 1
        })
        score += 1

    # Leadership hires for AI roles (HIGH weight)
    leadership_raw = enrichment.get("leadership_hire", "[]")
    ai_leadership_keywords = [
        "ai", "ml", "machine learning", "data", "chief scientist",
        "head of ai", "vp ai", "chief ai", "applied scientist"
    ]
    try:
        leadership_data = json.loads(leadership_raw) \
            if isinstance(leadership_raw, str) else []
        ai_hires = [h for h in leadership_data
                    if any(k in str(h.get("label", "")).lower()
                           for k in ai_leadership_keywords)]
        if ai_hires:
            signals.append({
                "signal": "ai_leadership_hire",
                "weight": "high",
                "detail": f"AI leadership hire detected: {ai_hires[0].get('label', '')[:80]}",
                "score_contribution": 1
            })
            score += 1
    except Exception:
        pass

    # Cap at 3
    score = min(score, 3)

    # Determine confidence
    if len(signals) >= 3:
        confidence = "high"
    elif len(signals) == 2:
        confidence = "medium"
    elif len(signals) == 1:
        confidence = "low"
    else:
        confidence = "very_low"

    # Determine pitch implication
    if score == 0:
        pitch = "Generic outreach — no AI angle"
    elif score == 1:
        pitch = "Segment 1/2 — standard pitch, no AI emphasis"
    elif score == 2:
        pitch = "Segment 1/2 with AI language OR Segment 4 if strong signals"
    else:
        pitch = "Segment 4 eligible — ML platform, agentic systems pitch"

    return {
        "company": company_name,
        "ai_maturity_score": score,
        "confidence": confidence,
        "signals": signals,
        "pitch_implication": pitch,
        "note": f"Score {score}/3 based on {len(signals)} public signals"
    }


if __name__ == "__main__":
    test_companies = ["Yellow.ai", "Consolety", "Williams Blackstock Architects"]

    for company in test_companies:
        print(f"\n{'='*50}")
        result = score_ai_maturity(company)
        print(f"Company: {result['company']}")
        print(f"AI Maturity Score: {result['ai_maturity_score']}/3")
        print(f"Confidence: {result['confidence']}")
        print(f"Pitch: {result['pitch_implication']}")
        print(f"Signals: {len(result['signals'])}")
        for s in result['signals']:
            print(f"  - [{s['weight']}] {s['signal']}: {s['detail']}")
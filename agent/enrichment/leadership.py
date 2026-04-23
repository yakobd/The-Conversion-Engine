import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.enrichment.crunchbase import enrich_company, load_crunchbase_data

def check_leadership_change(company_name: str) -> dict:
    """
    Detect recent CTO/VP Engineering changes using Crunchbase
    leadership_hire field.
    """
    enrichment = enrich_company(company_name)

    if not enrichment.get("found"):
        return {
            "company": company_name,
            "leadership_change_detected": False,
            "confidence": 0.0,
            "note": "Company not found in Crunchbase ODM sample"
        }

    leadership_raw = enrichment.get("leadership_hire", "[]")

    try:
        leadership_data = json.loads(leadership_raw) \
            if isinstance(leadership_raw, str) else leadership_raw
        has_change = isinstance(leadership_data, list) and len(leadership_data) > 0
    except Exception:
        has_change = False
        leadership_data = []

    # Filter for technical leadership roles
    technical_roles = [
        "cto", "chief technology", "vp engineering", "vp of engineering",
        "head of engineering", "chief engineer", "technical director",
        "chief ai", "vp product", "chief product"
    ]

    technical_hires = []
    if has_change:
        for hire in leadership_data:
            title = str(hire.get("title", "")).lower()
            if any(role in title for role in technical_roles):
                technical_hires.append(hire)

    if technical_hires:
        return {
            "company": company_name,
            "leadership_change_detected": True,
            "technical_leadership_change": True,
            "confidence": 1.0,
            "source": "crunchbase_odm",
            "hires": technical_hires,
            "icp_signal": "Segment 3 — leadership transition pitch",
            "note": "New technical leadership detected — vendor reassessment window"
        }

    if has_change:
        return {
            "company": company_name,
            "leadership_change_detected": True,
            "technical_leadership_change": False,
            "confidence": 0.8,
            "source": "crunchbase_odm",
            "hires": leadership_data[:3],
            "icp_signal": "Segment 1 or 2 — monitor for technical role",
            "note": "Leadership change detected but not technical role"
        }

    return {
        "company": company_name,
        "leadership_change_detected": False,
        "confidence": 0.9,
        "source": "crunchbase_odm",
        "note": "No recent leadership change detected"
    }


if __name__ == "__main__":
    df = load_crunchbase_data()

    # Find companies with leadership hires
    has_leadership = df[df['leadership_hire'].apply(
        lambda x: isinstance(x, str) and x != '[]' and len(x) > 5
    )]
    print(f"Companies with leadership hire data: {len(has_leadership)}")

    if len(has_leadership) > 0:
        test_company = has_leadership.iloc[0]['name']
        print(f"\nTesting with: {test_company}")
        result = check_leadership_change(test_company)
        print(json.dumps(result, indent=2))

    # Also test Yellow.ai
    print("\nTesting Yellow.ai:")
    result2 = check_leadership_change("Yellow.ai")
    print(json.dumps(result2, indent=2))
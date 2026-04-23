import json
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.enrichment.crunchbase import enrich_company, load_crunchbase_data

def check_layoffs(company_name: str) -> dict:
    """
    Check layoff signal using Crunchbase ODM layoff field.
    Falls back gracefully if data unavailable.
    """
    # First try Crunchbase ODM layoff field
    enrichment = enrich_company(company_name)

    if not enrichment.get("found"):
        return {
            "company": company_name,
            "layoff_detected": False,
            "confidence": 0.0,
            "source": "crunchbase_odm",
            "note": "Company not found in Crunchbase ODM sample"
        }

    layoff_raw = enrichment.get("layoff", "[]")

    try:
        layoff_data = json.loads(layoff_raw) if isinstance(layoff_raw, str) else layoff_raw
        layoff_detected = isinstance(layoff_data, list) and len(layoff_data) > 0
    except Exception:
        layoff_detected = False
        layoff_data = []

    if layoff_detected:
        latest = layoff_data[0] if layoff_data else {}
        return {
            "company": company_name,
            "layoff_detected": True,
            "confidence": 1.0,
            "source": "crunchbase_odm",
            "layoff_count": len(layoff_data),
            "latest_layoff": latest,
            "icp_signal": "Segment 2 — cost restructuring pitch",
            "note": "Recent layoff detected in Crunchbase data"
        }

    return {
        "company": company_name,
        "layoff_detected": False,
        "confidence": 0.9,
        "source": "crunchbase_odm",
        "note": "No layoff detected in Crunchbase ODM data"
    }


def check_layoffs_bulk(companies: list) -> list:
    """Check layoffs for multiple companies."""
    return [check_layoffs(c) for c in companies]


if __name__ == "__main__":
    df = load_crunchbase_data()
    # Find companies that have layoff data
    has_layoff = df[df['layoff'].apply(
        lambda x: isinstance(x, str) and x != '[]' and len(x) > 5
    )]
    print(f"Companies with layoff data: {len(has_layoff)}")

    if len(has_layoff) > 0:
        test_company = has_layoff.iloc[0]['name']
        print(f"\nTesting with: {test_company}")
        result = check_layoffs(test_company)
        print(json.dumps(result, indent=2))
    else:
        print("\nNo layoff data in current sample")
        print("Testing with Consolety:")
        result = check_layoffs("Consolety")
        print(json.dumps(result, indent=2))
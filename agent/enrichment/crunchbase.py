import pandas as pd
import json
from pathlib import Path

CRUNCHBASE_PATH = Path(__file__).parent.parent.parent / "Crunchbase-dataset-samples" / "crunchbase-companies-information.csv"

_df_cache = None

def load_crunchbase_data():
    global _df_cache
    if _df_cache is None:
        _df_cache = pd.read_csv(CRUNCHBASE_PATH)
    return _df_cache

def enrich_company(company_name: str) -> dict:
    """
    Look up a company in the Crunchbase ODM sample.
    Returns enrichment_brief.json structure.
    """
    df = load_crunchbase_data()
    company_lower = company_name.lower().strip()

    # Try exact match first
    match = df[df['name'].str.lower().str.strip() == company_lower]

    # Try partial match if no exact match
    if match.empty:
        match = df[df['name'].str.lower().str.contains(
            company_lower, na=False
        )]

    if match.empty:
        return {
            "company": company_name,
            "crunchbase_id": None,
            "found": False,
            "confidence": 0.0,
            "last_enriched_at": pd.Timestamp.now().isoformat(),
            "note": "No match found in Crunchbase ODM sample"
        }

    record = match.iloc[0].to_dict()
    confidence = 1.0 if len(match) == 1 else 0.8

    return {
        "company": company_name,
        "crunchbase_id": str(record.get("uuid", "unknown")),
        "found": True,
        "confidence": confidence,
        "last_enriched_at": pd.Timestamp.now().isoformat(),
        "name": str(record.get("name", "")),
        "website": str(record.get("website", "")),
        "description": str(record.get("about", "")),
        "industries": str(record.get("industries", "")),
        "operating_status": str(record.get("operating_status", "")),
        "company_type": str(record.get("company_type", "")),
        "founded_date": str(record.get("founded_date", "")),
        "num_employees": str(record.get("num_employees", "")),
        "country_code": str(record.get("country_code", "")),
        "location": str(record.get("location", "")),
        "funding_rounds": str(record.get("funding_rounds", "")),
        "funding_rounds_list": str(record.get("funding_rounds_list", "")),
        "num_investors": str(record.get("num_investors", "")),
        "layoff": str(record.get("layoff", "")),
        "leadership_hire": str(record.get("leadership_hire", "")),
        "builtwith_tech": str(record.get("builtwith_tech", "")),
        "stock_symbol": str(record.get("stock_symbol", "")),
        "ipo_status": str(record.get("ipo_status", "")),
    }


def get_sample_companies(n=5):
    """Return n sample company names from the dataset."""
    df = load_crunchbase_data()
    return df['name'].head(n).tolist()


if __name__ == "__main__":
    # Show sample companies
    samples = get_sample_companies(10)
    print("Sample companies in dataset:")
    for s in samples:
        print(f"  - {s}")

    # Test with first company
    print(f"\nEnriching: {samples[0]}")
    result = enrich_company(samples[0])
    print(json.dumps(result, indent=2))
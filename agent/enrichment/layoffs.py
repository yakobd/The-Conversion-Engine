import json
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.enrichment.crunchbase import enrich_company, load_crunchbase_data

LAYOFFS_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "layoffs_cache.csv"
LAYOFFS_GITHUB_URL = "https://raw.githubusercontent.com/SaiPrabandh/eda-on-layoffs.csv/main/layoffs.csv"

_layoffs_df_cache = None

def load_layoffs_data() -> pd.DataFrame:
    """Load layoffs data from cache file."""
    global _layoffs_df_cache
    if _layoffs_df_cache is not None:
        return _layoffs_df_cache
    if LAYOFFS_CACHE_PATH.exists():
        _layoffs_df_cache = pd.read_csv(LAYOFFS_CACHE_PATH)
        return _layoffs_df_cache
    return pd.DataFrame()


def check_layoffs_live(company_name: str) -> dict:
    """
    Check layoffs data from GitHub-hosted CSV (2,362 real records).
    Source: github.com/SaiPrabandh/eda-on-layoffs.csv
    """
    df = load_layoffs_data()

    if df.empty:
        return {
            "company": company_name,
            "layoff_detected": False,
            "confidence": 0.0,
            "source": "layoffs_csv_unavailable",
            "note": "Layoffs CSV not available"
        }

    company_lower = company_name.lower().strip()

    # Try exact match first
    match = df[df['company'].str.lower().str.strip() == company_lower]

    # Try partial match
    if match.empty:
        match = df[df['company'].str.lower().str.contains(
            company_lower, na=False, regex=False
        )]

    if match.empty:
        return {
            "company": company_name,
            "layoff_detected": False,
            "confidence": 0.9,
            "source": "layoffs_fyi_github_mirror",
            "note": "No layoff found in 2362-record dataset"
        }

    record = match.iloc[0].to_dict()
    total_laid_off = record.get("total_laid_off", "unknown")
    percentage = record.get("percentage_laid_off", "unknown")
    date = record.get("date", "unknown")
    stage = record.get("stage", "unknown")

    return {
        "company": company_name,
        "layoff_detected": True,
        "confidence": 1.0,
        "source": "layoffs_fyi_github_mirror",
        "total_laid_off": str(total_laid_off),
        "percentage_laid_off": str(percentage),
        "date": str(date),
        "stage": str(stage),
        "country": str(record.get("country", "")),
        "icp_signal": "Segment 2 — cost restructuring pitch",
        "note": f"Layoff detected from layoffs.fyi dataset ({len(match)} records found)"
    }


def check_layoffs(company_name: str) -> dict:
    """
    Check layoff signal — tries live CSV first, falls back to Crunchbase.
    """
    # Try live CSV first
    live_result = check_layoffs_live(company_name)
    if live_result.get("layoff_detected") or live_result.get("confidence", 0) >= 0.9:
        return live_result

    # Fall back to Crunchbase layoff field
    enrichment = enrich_company(company_name)
    if not enrichment.get("found"):
        return {
            "company": company_name,
            "layoff_detected": False,
            "confidence": 0.0,
            "source": "crunchbase_odm",
            "note": "Company not found in either source"
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
            "note": "Layoff detected via Crunchbase ODM"
        }

    return {
        "company": company_name,
        "layoff_detected": False,
        "confidence": 0.9,
        "source": "crunchbase_odm",
        "note": "No layoff detected in either layoffs.fyi dataset or Crunchbase"
    }


if __name__ == "__main__":
    df = load_layoffs_data()
    print(f"Layoffs dataset loaded: {len(df)} records")
    print(f"Columns: {list(df.columns)}")

    # Test with known companies
    for company in ["Atlassian", "Yellow.ai", "Google", "Consolety"]:
        result = check_layoffs(company)
        print(f"\n{company}:")
        print(f"  Detected: {result['layoff_detected']}")
        print(f"  Source: {result['source']}")
        if result['layoff_detected']:
            print(f"  Total laid off: {result.get('total_laid_off', 'N/A')}")
            print(f"  Date: {result.get('date', 'N/A')}")
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.enrichment.crunchbase import load_crunchbase_data, enrich_company
from agent.enrichment.ai_maturity import score_ai_maturity

OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "enrichment_outputs"

def get_sector_competitors(company_name: str, max_competitors: int = 10) -> list:
    """
    Find top companies in the same sector from Crunchbase ODM.
    """
    df = load_crunchbase_data()
    prospect = enrich_company(company_name)

    if not prospect.get("found"):
        return []

    # Get prospect industry
    prospect_industry = prospect.get("industries", "").lower()

    if not prospect_industry or prospect_industry == "nan":
        # Fall back to random sample from dataset
        return df.sample(min(max_competitors, len(df)))['name'].tolist()

    # Extract first industry keyword
    try:
        import re
        # Extract value fields from JSON-like string
        values = re.findall(r'"value"\s*:\s*"([^"]+)"', prospect_industry)
        if values:
            primary_industry = values[0].lower()
        else:
            primary_industry = prospect_industry[:20]
    except Exception:
        primary_industry = ""

    # Find companies in same sector
    if primary_industry:
            import re
            safe_pattern = re.escape(primary_industry)
            sector_companies = df[
                df['industries'].str.lower().str.contains(
                    safe_pattern, na=False, regex=True
                ) & (df['name'] != company_name)
            ]['name'].tolist()
    else:
        sector_companies = df[df['name'] != company_name]['name'].tolist()

    return sector_companies[:max_competitors]


def generate_competitor_gap_brief(company_name: str) -> dict:
    """
    Generate competitor_gap_brief.json for a prospect.
    Compares prospect AI maturity against top-quartile sector peers.
    """
    print(f"\n📊 Generating competitor gap brief for: {company_name}")

    # Score prospect
    prospect_score = score_ai_maturity(company_name)
    prospect_ai = prospect_score.get("ai_maturity_score", 0)

    # Get competitors
    competitors = get_sector_competitors(company_name, max_competitors=10)
    print(f"  Found {len(competitors)} sector peers")

    # Score each competitor
    competitor_scores = []
    for comp in competitors:
        score = score_ai_maturity(comp)
        competitor_scores.append({
            "company": comp,
            "ai_maturity_score": score.get("ai_maturity_score", 0),
            "confidence": score.get("confidence", "low"),
            "signals": score.get("signals", [])
        })

    if not competitor_scores:
            # Fall back to random sample from dataset
            df = load_crunchbase_data()
            fallback = df[df['name'] != company_name]['name'].sample(
                min(10, len(df))
            ).tolist()
            for comp in fallback:
                score = score_ai_maturity(comp)
                competitor_scores.append({
                    "company": comp,
                    "ai_maturity_score": score.get("ai_maturity_score", 0),
                    "confidence": score.get("confidence", "low"),
                    "signals": score.get("signals", [])
                })
            print(f"  Using {len(competitor_scores)} random sector peers as fallback")

    # Calculate sector statistics
    scores_list = [c["ai_maturity_score"] for c in competitor_scores]
    avg_score = sum(scores_list) / len(scores_list)
    max_score = max(scores_list)
    top_quartile_threshold = sorted(scores_list)[-max(1, len(scores_list)//4)]

    # Find top quartile companies
    top_quartile = [
        c for c in competitor_scores
        if c["ai_maturity_score"] >= top_quartile_threshold
        and c["ai_maturity_score"] > 0
    ]

    # Find practices prospect is missing
    prospect_signals = set(
        s.get("signal", "") for s in prospect_score.get("signals", [])
    )

    gaps = []
    for tq_company in top_quartile[:3]:
        for signal in tq_company.get("signals", []):
            sig_name = signal.get("signal", "")
            if sig_name not in prospect_signals:
                gaps.append({
                    "practice": sig_name,
                    "detail": signal.get("detail", ""),
                    "example_company": tq_company["company"],
                    "weight": signal.get("weight", "medium")
                })

    # Deduplicate gaps
    seen_practices = set()
    unique_gaps = []
    for g in gaps:
        if g["practice"] not in seen_practices:
            seen_practices.add(g["practice"])
            unique_gaps.append(g)

    # Prospect position in sector
    prospect_rank = len([s for s in scores_list if s > prospect_ai]) + 1
    sector_size = len(scores_list) + 1

    brief = {
        "prospect": company_name,
        "generated_at": datetime.now().isoformat(),
        "prospect_ai_maturity": prospect_ai,
        "sector_stats": {
            "avg_ai_maturity": round(avg_score, 2),
            "max_ai_maturity": max_score,
            "top_quartile_threshold": top_quartile_threshold,
            "sector_size_in_sample": sector_size
        },
        "prospect_position": {
            "rank": prospect_rank,
            "out_of": sector_size,
            "percentile": round((1 - prospect_rank/sector_size) * 100, 1),
            "vs_average": prospect_ai - avg_score
        },
        "top_quartile_companies": top_quartile[:5],
        "capability_gaps": unique_gaps[:3],
        "outreach_finding": generate_gap_finding(
            company_name, prospect_ai, avg_score, unique_gaps
        )
    }

    # Save output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = company_name.replace(" ", "_").replace("/", "_").lower()
    output_path = OUTPUT_DIR / f"competitor_gap_brief_{safe_name}.json"
    with open(output_path, "w") as f:
        json.dump(brief, f, indent=2)

    print(f"  ✅ Saved to {output_path}")
    return brief


def generate_gap_finding(
    company_name: str,
    prospect_score: int,
    avg_score: float,
    gaps: list
) -> str:
    """Generate a human-readable research finding for outreach."""
    if not gaps:
        if prospect_score >= 2:
            return (
                f"{company_name} shows strong AI signals relative to peers. "
                f"The opportunity is specialized capacity — ML engineers and "
                f"AI systems builders — not direction."
            )
        return (
            f"Most companies in {company_name}'s sector are at an early stage "
            f"of AI adoption. The window to build a first-mover advantage is open."
        )

    gap_names = [g["practice"].replace("_", " ") for g in gaps[:2]]
    gap_str = " and ".join(gap_names)

    if prospect_score < avg_score:
        return (
            f"Companies at {company_name}'s stage in this sector show public "
            f"signals of {gap_str}. That gap is where the engineering bottleneck "
            f"typically appears first."
        )
    return (
        f"{company_name} is ahead of sector average on AI signals. "
        f"Peers investing in {gap_str} are pulling further ahead. "
        f"The constraint shifts to execution speed."
    )


if __name__ == "__main__":
    brief = generate_competitor_gap_brief("Yellow.ai")
    print(f"\n{'='*60}")
    print(f"Prospect AI Score: {brief['prospect_ai_maturity']}/3")
    print(f"Sector Average: {brief['sector_stats']['avg_ai_maturity']}/3")
    print(f"Prospect Rank: {brief['prospect_position']['rank']} of {brief['prospect_position']['out_of']}")
    print(f"\nCapability Gaps ({len(brief['capability_gaps'])}):")
    for gap in brief['capability_gaps']:
        print(f"  - {gap['practice']}: {gap['detail'][:60]}")
    print(f"\nOutreach Finding:")
    print(f"  {brief['outreach_finding']}")
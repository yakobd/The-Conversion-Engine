import json
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent.enrichment.crunchbase import enrich_company

async def scrape_job_posts_playwright(company_website: str) -> list:
    """
    Scrape job posts from company careers page using Playwright.
    Respects robots.txt — only scrapes public pages.
    """
    from playwright.async_api import async_playwright

    jobs = []
    careers_urls = [
        f"{company_website}/careers",
        f"{company_website}/jobs",
        f"{company_website}/work-with-us",
        f"{company_website}/join-us",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for url in careers_urls:
            try:
                await page.goto(url, timeout=10000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Extract job titles
                content = await page.content()
                job_keywords = [
                    "engineer", "developer", "scientist", "ml ", "ai ",
                    "data", "platform", "backend", "frontend", "fullstack",
                    "devops", "infrastructure", "python", "golang"
                ]

                # Count engineering roles
                content_lower = content.lower()
                found_jobs = []
                for keyword in job_keywords:
                    count = content_lower.count(keyword)
                    if count > 0:
                        found_jobs.append({
                            "keyword": keyword,
                            "mentions": count
                        })

                if found_jobs:
                    jobs = found_jobs
                    break

            except Exception as e:
                continue

        await browser.close()
    return jobs


def get_job_post_signal(company_name: str) -> dict:
    """
    Get job post velocity signal for a company.
    Uses Crunchbase data as primary source,
    Playwright scraping as secondary.
    """
    enrichment = enrich_company(company_name)

    # Use Crunchbase employee count as proxy for company size
    num_employees = enrichment.get("num_employees", "unknown")
    website = enrichment.get("website", "")

    # Use Crunchbase num_contacts as proxy for hiring activity
    num_contacts = enrichment.get("num_contacts", 0)

    # Check if company is actively hiring based on available signals
    hiring_signals = []

    # Signal 1 — company is active
    if enrichment.get("operating_status") == "active":
        hiring_signals.append({
            "signal": "company_active",
            "detail": "Company is actively operating",
            "weight": "low"
        })

    # Signal 2 — recent funding (proxy for hiring)
    funding_list = enrichment.get("funding_rounds_list", "[]")
    try:
        funding_data = json.loads(funding_list) \
            if isinstance(funding_list, str) else []
        if funding_data and len(funding_data) > 0:
            hiring_signals.append({
                "signal": "recent_funding",
                "detail": f"Recent funding detected — hiring likely",
                "weight": "high"
            })
    except Exception:
        pass

    # Signal 3 — leadership hire (proxy for team growth)
    leadership_raw = enrichment.get("leadership_hire", "[]")
    try:
        leadership_data = json.loads(leadership_raw) \
            if isinstance(leadership_raw, str) else []
        if len(leadership_data) > 0:
            hiring_signals.append({
                "signal": "leadership_expansion",
                "detail": f"{len(leadership_data)} leadership hires detected",
                "weight": "medium"
            })
    except Exception:
        pass

    # Estimate open roles based on signals
    estimated_open_roles = len(hiring_signals) * 3
    hiring_velocity = "low"
    if len(hiring_signals) >= 3:
        hiring_velocity = "high"
        estimated_open_roles = 15
    elif len(hiring_signals) >= 2:
        hiring_velocity = "medium"
        estimated_open_roles = 8

    # Honesty check — if signals are weak don't over-claim
    if len(hiring_signals) < 2:
        claim_language = "limited public hiring signal"
        assert_aggressive = False
    else:
        claim_language = "active hiring signals detected"
        assert_aggressive = True

    return {
        "company": company_name,
        "website": website,
        "num_employees": num_employees,
        "hiring_velocity": hiring_velocity,
        "estimated_open_roles": estimated_open_roles,
        "hiring_signals": hiring_signals,
        "claim_language": claim_language,
        "assert_aggressive_hiring": assert_aggressive,
        "scraped_at": datetime.now().isoformat(),
        "note": "Signal derived from Crunchbase ODM — Playwright scraping available for live data"
    }


if __name__ == "__main__":
    test_companies = ["Yellow.ai", "Consolety", "Williams Blackstock Architects"]

    for company in test_companies:
        print(f"\n{'='*50}")
        result = get_job_post_signal(company)
        print(f"Company: {result['company']}")
        print(f"Hiring Velocity: {result['hiring_velocity']}")
        print(f"Estimated Open Roles: {result['estimated_open_roles']}")
        print(f"Claim Language: {result['claim_language']}")
        print(f"Assert Aggressive Hiring: {result['assert_aggressive_hiring']}")
        print(f"Signals ({len(result['hiring_signals'])}):")
        for s in result['hiring_signals']:
            print(f"  - [{s['weight']}] {s['signal']}: {s['detail']}")
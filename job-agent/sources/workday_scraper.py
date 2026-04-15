"""
Workday career portal scraper (Phase 5 — requires Playwright).

Workday is used by most Fortune 500 companies. There is no public API,
so we use Playwright (headless Chromium) to visit career pages and extract listings.

Install Playwright: pip install playwright && playwright install chromium
"""

import asyncio
import logging
import time
from typing import Optional

from config import WORKDAY_COMPANIES, ROLE_KEYWORDS, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)


def _is_relevant(title: str) -> bool:
    title_lower = title.lower()
    if not any(kw in title_lower for kw in ROLE_KEYWORDS):
        return False
    if any(kw in title_lower for kw in EXCLUDE_KEYWORDS):
        return False
    return True


async def _scrape_url_async(url: str, company_name: str, keywords: list[str]) -> list[dict]:
    """Async Playwright scraper for a single company career URL."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []

    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            logger.info("Playwright visiting: %s", url)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)  # allow JS to render

            # Generic job card extraction — looks for common job listing patterns
            job_elements = await page.query_selector_all(
                "a[href*='job'], a[href*='career'], [data-automation-id='jobTitle'], "
                ".job-title, .position-title, [class*='jobTitle'], [class*='job-title']"
            )

            for elem in job_elements:
                title = await elem.inner_text()
                title = title.strip()
                if not title or len(title) < 5:
                    continue

                href = await elem.get_attribute("href") or ""
                if href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"

                if not _is_relevant(title):
                    continue

                # Check if any company-specific keywords match
                if keywords and not any(kw.lower() in title.lower() for kw in keywords):
                    continue

                jobs.append({
                    "title": title,
                    "company": company_name,
                    "url": href or url,
                    "jd_text": "",  # extracted later by jd_extractor
                    "source": "workday",
                    "posted_date": "",
                })

        except Exception as e:
            logger.error("Playwright scrape failed for %s: %s", url, e)
        finally:
            await browser.close()

    # Deduplicate by (company, title)
    seen = set()
    unique_jobs = []
    for job in jobs:
        key = (job["company"], job["title"])
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    logger.info("Workday scraper found %d jobs at %s", len(unique_jobs), company_name)
    return unique_jobs


def scrape_workday(company_config: dict) -> list[dict]:
    """
    Scrape a single Workday-based company career page.

    Args:
        company_config: Dict with keys: name, url, keywords (list)

    Returns:
        List of job dicts.
    """
    return asyncio.run(
        _scrape_url_async(
            url=company_config["url"],
            company_name=company_config["name"],
            keywords=company_config.get("keywords", []),
        )
    )


def fetch_workday_jobs(companies: Optional[list] = None) -> list[dict]:
    """
    Scrape all configured Workday company career pages.

    Args:
        companies: List of company config dicts.
                   Defaults to config.WORKDAY_COMPANIES.

    Returns:
        List of all job dicts found.
    """
    if companies is None:
        companies = WORKDAY_COMPANIES

    all_jobs: list[dict] = []

    for company_config in companies:
        try:
            jobs = scrape_workday(company_config)
            all_jobs.extend(jobs)
            time.sleep(2)  # polite delay between companies
        except Exception as e:
            logger.error("Workday scrape failed for %s: %s", company_config.get("name"), e)

    logger.info("Workday total: %d jobs scraped", len(all_jobs))
    return all_jobs

from typing import List, Dict, Any, Optional
import httpx
import structlog

from src.config import settings
from src.agents.pii_scrubber import scrub_pii

logger = structlog.get_logger(__name__)


async def _query_searxng(
    client: httpx.AsyncClient,
    query: str,
    base_url: str,
) -> List[Dict[str, str]]:
    """Query SearXNG local instance with JSON format."""
    url = f"{base_url.rstrip('/')}/search"
    params = {"q": query, "format": "json"}
    try:
        response = await client.get(url, params=params, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            raw_results = data.get("results", [])
            results = []
            for item in raw_results:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "") or item.get("snippet", ""),
                    "engine": "searxng",
                })
            return results
    except Exception as exc:
        logger.warning("SearXNG query failed", query=query, error=str(exc))
    return []


async def _query_tavily(
    client: httpx.AsyncClient,
    query: str,
    api_key: str,
) -> List[Dict[str, str]]:
    """Fallback query to Tavily API."""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "max_results": 5,
    }
    try:
        response = await client.post(url, json=payload, timeout=6.0)
        if response.status_code == 200:
            data = response.json()
            raw_results = data.get("results", [])
            results = []
            for item in raw_results:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "") or item.get("snippet", ""),
                    "engine": "tavily",
                })
            return results
    except Exception as exc:
        logger.warning("Tavily query failed", query=query, error=str(exc))
    return []


async def execute_osint_queries(
    person_a: str,
    person_b: str,
    shared_org: str,
    searxng_url: Optional[str] = None,
    tavily_api_key: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Executes targeted OSINT searches for potential connection between person_a and person_b
    at shared_org.
    1. Scrubs PII from names and organization.
    2. Builds two high-precision search queries.
    3. Queries SearXNG first; falls back to Tavily if SearXNG is unavailable or returns < 2 results.
    4. Returns deduplicated results.
    """
    clean_a = scrub_pii(person_a)
    clean_b = scrub_pii(person_b)
    clean_org = scrub_pii(shared_org)

    target_searxng_url = searxng_url or settings.SEARXNG_URL
    target_tavily_key = tavily_api_key or settings.TAVILY_API_KEY

    q1 = f'"{clean_a}" "{clean_b}" "{clean_org}"'
    q2 = f'"{clean_b}" "{clean_org}" (site:linkedin.com/in OR site:github.com OR site:ieeexplore.org OR site:arxiv.org)'
    queries = [q1, q2]

    all_results: List[Dict[str, str]] = []
    seen_urls = set()

    async with httpx.AsyncClient() as client:
        for q in queries:
            results = await _query_searxng(client, q, target_searxng_url)

            # Fallback to Tavily if results < 2 and Tavily key is configured
            if len(results) < 2 and target_tavily_key:
                tavily_res = await _query_tavily(client, q, target_tavily_key)
                results.extend(tavily_res)

            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)

    logger.info(
        "OSINT recon completed",
        person_a=clean_a,
        person_b=clean_b,
        shared_org=clean_org,
        results_count=len(all_results),
    )
    return all_results

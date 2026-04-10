"""NIH Reporter v2 API client."""

import asyncio
import httpx
from typing import Any

BASE_URL = "https://reporter.nih.gov/api/v2/projects/search"

DEFAULT_FIELDS = [
    "project_title",
    "abstract_text",
    "award_amount",
    "pi_names",
    "org_name",
    "fiscal_year",
    "project_num",
    "project_start_date",
    "project_end_date",
    "agency_code",
    "department",
    "opportunity_number",
    "project_detail_url",
]

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "GrantDiscoveryMCP/1.0 (research aggregation tool)",
}


def _pi_names(pi_list: list[dict] | None) -> str:
    if not pi_list:
        return "N/A"
    names = []
    for pi in pi_list:
        first = pi.get("first_name", "")
        last = pi.get("last_name", "")
        names.append(f"{first} {last}".strip())
    return ", ".join(names) if names else "N/A"


async def _post_with_retry(payload: dict, retries: int = 3) -> dict:
    """POST to NIH Reporter with exponential backoff retries."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(BASE_URL, json=payload, headers=HEADERS)
                if resp.status_code == 500:
                    raise httpx.HTTPStatusError(
                        f"NIH Reporter returned 500 (attempt {attempt + 1}/{retries}) — "
                        "the NIH API may be temporarily unavailable.",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)

    raise last_exc or RuntimeError("NIH Reporter request failed after retries")


async def search(
    keyword: str,
    fiscal_years: list[int] | None = None,
    limit: int = 10,
    pi_first: str | None = None,
    pi_last: str | None = None,
    institution: str | None = None,
    project_num: str | None = None,
) -> list[dict[str, Any]]:
    criteria: dict[str, Any] = {}

    if keyword:
        criteria["advanced_text_search"] = {
            "operator": "and",
            "search_field": "all",
            "search_text": keyword,
        }

    if fiscal_years:
        criteria["fiscal_years"] = fiscal_years

    if pi_first or pi_last:
        pi_filter: dict[str, Any] = {}
        if pi_first:
            pi_filter["first_name"] = pi_first
        if pi_last:
            pi_filter["last_name"] = pi_last
        criteria["pi_names"] = [pi_filter]

    if institution:
        criteria["org_names"] = [institution]

    if project_num:
        criteria["project_nums"] = [project_num]

    payload = {
        "criteria": criteria,
        "limit": min(limit, 500),
        "offset": 0,
        "fields": DEFAULT_FIELDS,
    }

    data = await _post_with_retry(payload)
    results = data.get("results", [])
    parsed = []
    for r in results:
        parsed.append(
            {
                "source": "NIH",
                "grant_id": r.get("project_num", "N/A"),
                "title": r.get("project_title", "N/A"),
                "pi": _pi_names(r.get("pi_names")),
                "institution": r.get("org_name", "N/A"),
                "department": r.get("department", "N/A"),
                "amount": r.get("award_amount"),
                "year": r.get("fiscal_year"),
                "abstract": r.get("abstract_text", ""),
                "start_date": r.get("project_start_date", "N/A"),
                "end_date": r.get("project_end_date", "N/A"),
                "agency": r.get("agency_code", "NIH"),
                "opportunity_number": r.get("opportunity_number", "N/A"),
                "url": r.get("project_detail_url", ""),
            }
        )
    return parsed


async def search_by_year(keyword: str, year: int) -> dict[str, Any]:
    """Returns count and total funding for a keyword in a given fiscal year."""
    payload = {
        "criteria": {
            "advanced_text_search": {
                "operator": "and",
                "search_field": "all",
                "search_text": keyword,
            },
            "fiscal_years": [year],
        },
        "limit": 500,
        "offset": 0,
        "fields": ["award_amount", "fiscal_year"],
    }

    data = await _post_with_retry(payload)
    results = data.get("results", [])
    total = sum(r.get("award_amount") or 0 for r in results)
    return {"count": len(results), "total": total, "year": year}

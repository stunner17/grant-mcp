"""Grants.gov search API client for open funding opportunities."""

import httpx
from typing import Any

SEARCH_URL = "https://apply07.grants.gov/grantsws/rest/opportunities/search"


def _parse_date(val: str | None) -> str:
    if not val:
        return "N/A"
    # Dates come as millisecond timestamps or MM/DD/YYYY strings
    if isinstance(val, (int, float)):
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(val / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    return str(val)


async def search_opportunities(
    keyword: str = "",
    agency: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "rows": min(limit, 25),
        "oppStatuses": "forecasted|posted",  # Only open opportunities
    }

    if keyword:
        payload["keyword"] = keyword
    if agency:
        payload["agencies"] = agency

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            SEARCH_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    opps = data.get("oppHits", []) or []
    parsed = []
    for o in opps:
        # Max award may be in awardCeiling
        max_award = o.get("awardCeiling")
        if max_award:
            try:
                max_award = f"${int(max_award):,}"
            except (ValueError, TypeError):
                max_award = str(max_award)

        eligibility_codes = o.get("eligibilities", []) or []
        eligibility = ", ".join(eligibility_codes) if eligibility_codes else "See opportunity"

        parsed.append(
            {
                "source": "Grants.gov",
                "opportunity_id": o.get("id", "N/A"),
                "title": o.get("title", "N/A"),
                "agency": o.get("agencyName", o.get("agency", "N/A")),
                "status": o.get("oppStatus", "N/A"),
                "deadline": _parse_date(o.get("closeDate")),
                "posted_date": _parse_date(o.get("openDate")),
                "eligibility": eligibility,
                "max_award": max_award or "Not specified",
                "description": o.get("synopsis", o.get("description", "")),
                "url": f"https://www.grants.gov/search-results-detail/{o.get('id', '')}",
            }
        )
    return parsed

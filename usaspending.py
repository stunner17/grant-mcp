"""USASpending.gov API client — covers DOE, USDA, NASA, DARPA and all federal agencies."""

import httpx
from typing import Any

BASE_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

# Award type codes: 02=Block Grant, 03=Formula Grant, 04=Project Grant, 05=Cooperative Agreement
GRANT_TYPES = ["02", "03", "04", "05"]

FIELDS = [
    "Award ID",
    "Recipient Name",
    "Award Amount",
    "Awarding Agency",
    "Awarding Subtier Agency",
    "Description",
    "Start Date",
    "End Date",
]

# Agency name mapping for top-tier vs subtier agencies
AGENCY_MAP: dict[str, dict[str, Any]] = {
    "doe": {
        "label": "DOE",
        "filter": {"type": "awarding", "tier": "toptier", "name": "Department of Energy"},
    },
    "usda": {
        "label": "USDA",
        "filter": {"type": "awarding", "tier": "toptier", "name": "Department of Agriculture"},
    },
    "nasa": {
        "label": "NASA",
        "filter": {
            "type": "awarding",
            "tier": "toptier",
            "name": "National Aeronautics and Space Administration",
        },
    },
    "darpa": {
        "label": "DARPA",
        "filter": {
            "type": "awarding",
            "tier": "subtier",
            "name": "Defense Advanced Research Projects Agency",
        },
    },
}


def _build_payload(
    keyword: str = "",
    agencies: list[str] | None = None,
    year: int | None = None,
    limit: int = 10,
    recipient: str = "",
    institution: str = "",
) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "award_type_codes": GRANT_TYPES,
    }

    if keyword:
        filters["keywords"] = [keyword]

    if year:
        filters["time_period"] = [
            {"start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}
        ]

    if agencies:
        agency_filters = []
        for ag in agencies:
            info = AGENCY_MAP.get(ag.lower())
            if info:
                agency_filters.append(info["filter"])
        if agency_filters:
            filters["agencies"] = agency_filters

    if recipient:
        filters["recipient_search_text"] = [recipient]

    if institution:
        filters["recipient_search_text"] = [institution]

    return {
        "filters": filters,
        "fields": FIELDS,
        "page": 1,
        "limit": min(limit, 100),
        "sort": "Award Amount",
        "order": "desc",
    }


def _parse(results: list[dict]) -> list[dict[str, Any]]:
    parsed = []
    for r in results:
        agency = r.get("Awarding Subtier Agency") or r.get("Awarding Agency") or "Federal"
        desc = r.get("Description", "") or ""
        # USASpending descriptions are ALL CAPS — convert to title case for readability
        desc = desc.capitalize()

        start = r.get("Start Date", "N/A") or "N/A"
        year = start[:4] if start != "N/A" else "N/A"

        amount = r.get("Award Amount")
        try:
            amount = int(float(amount)) if amount else None
        except (ValueError, TypeError):
            amount = None

        parsed.append(
            {
                "source": "USASpending",
                "grant_id": r.get("Award ID", "N/A"),
                "title": desc[:120] + "…" if len(desc) > 120 else desc,
                "pi": "N/A",  # USASpending doesn't expose PI names
                "institution": (r.get("Recipient Name") or "N/A").title(),
                "department": "N/A",
                "amount": amount,
                "year": year,
                "abstract": desc,
                "start_date": start,
                "end_date": r.get("End Date", "N/A") or "N/A",
                "agency": agency,
                "opportunity_number": "N/A",
                "url": f"https://www.usaspending.gov/award/{r.get('generated_internal_id', '')}",
            }
        )
    return parsed


async def search(
    keyword: str = "",
    agencies: list[str] | None = None,
    year: int | None = None,
    limit: int = 10,
    institution: str = "",
) -> list[dict[str, Any]]:
    payload = _build_payload(
        keyword=keyword,
        agencies=agencies,
        year=year,
        limit=limit,
        institution=institution,
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(BASE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return _parse(data.get("results", []))


async def search_by_year(
    keyword: str,
    year: int,
    agencies: list[str] | None = None,
) -> dict[str, Any]:
    """Returns count and total funding for a keyword in a given year."""
    payload = _build_payload(keyword=keyword, agencies=agencies, year=year, limit=100)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(BASE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    total = sum(int(float(r.get("Award Amount") or 0)) for r in results)
    return {"count": len(results), "total": total, "year": year}

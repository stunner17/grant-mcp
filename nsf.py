"""NSF Awards API client."""

import httpx
from typing import Any

BASE_URL = "https://api.nsf.gov/services/v1/awards.json"

PRINT_FIELDS = (
    "id,title,abstractText,fundsObligatedAmt,piFirstName,piLastName,"
    "awardeeName,date,startDate,expDate,agency,primaryProgram"
)


async def search(
    keyword: str = "",
    pi_first: str = "",
    pi_last: str = "",
    institution: str = "",
    year: int | None = None,
    limit: int = 10,
    award_id: str = "",
) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "printFields": PRINT_FIELDS,
        "rpp": str(min(limit, 25)),  # NSF max is 25 per page
    }

    if keyword:
        params["keyword"] = keyword
    if pi_first:
        params["piFirstName"] = pi_first
    if pi_last:
        params["piLastName"] = pi_last
    if institution:
        params["awardeeName"] = institution
    if year:
        # NSF date filter: awards starting in that year
        params["dateStart"] = f"01/01/{year}"
        params["dateEnd"] = f"12/31/{year}"
    if award_id:
        params["id"] = award_id

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    awards = data.get("response", {}).get("award", []) or []
    parsed = []
    for a in awards:
        pi_name = f"{a.get('piFirstName', '')} {a.get('piLastName', '')}".strip() or "N/A"
        try:
            amount = int(a.get("fundsObligatedAmt", 0) or 0)
        except (ValueError, TypeError):
            amount = None

        # Extract year from date field (format: MM/DD/YYYY)
        date_str = a.get("date", "") or ""
        award_year = date_str.split("/")[-1] if date_str else "N/A"

        # pi field may be a list of "Name email" strings
        pi_list = a.get("pi", [])
        if pi_list and isinstance(pi_list, list):
            pi_name = pi_list[0].split(" ")[0] + " " + pi_list[0].split(" ")[1] if len(pi_list[0].split(" ")) >= 2 else pi_list[0]
        else:
            pi_name = f"{a.get('piFirstName', '')} {a.get('piLastName', '')}".strip() or "N/A"

        # primaryProgram may be a list
        primary_prog = a.get("primaryProgram", "N/A")
        if isinstance(primary_prog, list):
            primary_prog = primary_prog[0] if primary_prog else "N/A"

        # fundsObligatedAmt may be a string
        if amount is None or amount == 0:
            try:
                amount = int(a.get("estimatedTotalAmt", 0) or 0)
            except (ValueError, TypeError):
                pass

        parsed.append(
            {
                "source": "NSF",
                "grant_id": a.get("id", "N/A"),
                "title": a.get("title", "N/A"),
                "pi": pi_name,
                "institution": a.get("awardeeName", a.get("awardee", "N/A")),
                "department": primary_prog,
                "amount": amount,
                "year": award_year,
                "abstract": a.get("abstractText", ""),
                "start_date": a.get("startDate", "N/A"),
                "end_date": a.get("expDate", "N/A"),
                "agency": "NSF",
                "opportunity_number": "N/A",
                "url": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={a.get('id', '')}",
            }
        )
    return parsed


async def search_by_year(keyword: str, year: int) -> dict[str, Any]:
    """Returns count and total funding for a keyword in a given year."""
    params = {
        "keyword": keyword,
        "dateStart": f"01/01/{year}",
        "dateEnd": f"12/31/{year}",
        "printFields": "id,fundsObligatedAmt",
        "rpp": "25",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    awards = data.get("response", {}).get("award", []) or []
    total = sum(int(a.get("fundsObligatedAmt", 0) or 0) for a in awards)
    return {"count": len(awards), "total": total, "year": year}

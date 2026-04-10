"""
Grant & Funding Discovery MCP Server
Searches NIH, NSF, DOE, USDA, NASA, DARPA, and Grants.gov via plain-English queries.
Run: uvicorn main:app --host 0.0.0.0 --port 8000
"""

import asyncio
from typing import Any
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

import nih
import nsf
import grants_gov
import usaspending
import formatters

VERSION = "2.0.0"
TOOLS = [
    "search_grants",
    "get_grant_details",
    "search_by_pi",
    "search_by_institution",
    "find_open_opportunities",
    "get_funding_trends",
]

# Agencies served via USASpending
USA_AGENCIES = {"doe", "usda", "nasa", "darpa"}

mcp = FastMCP(
    name="Grant & Funding Discovery",
    version=VERSION,
    instructions=(
        "Search for research grants from NIH, NSF, DOE, USDA, NASA, DARPA, and Grants.gov. "
        "Use search_grants for keyword discovery, get_grant_details for full info, "
        "search_by_pi for a researcher's portfolio, search_by_institution for org-level data, "
        "find_open_opportunities for active funding calls, and get_funding_trends for trend analysis."
    ),
)


# ---------------------------------------------------------------------------
# Tool 1 — search_grants
# ---------------------------------------------------------------------------
@mcp.tool()
async def search_grants(
    keyword: str,
    agency: str = "all",
    year: int = 2024,
    limit: int = 10,
) -> str:
    """
    Search for awarded research grants by topic/keyword.

    Args:
        keyword: Topic or subject to search (e.g. "mRNA vaccines", "climate change")
        agency:  Source to search — "all", "nih", "nsf", "doe", "usda", "nasa", "darpa" (default: "all")
        year:    Fiscal/award year to filter by (default: 2024)
        limit:   Max results per source (default: 10)
    """
    agency = agency.lower()
    errors: list[str] = []

    # Determine which USASpending agencies to query
    usa_targets = [a for a in USA_AGENCIES if agency in ("all", a)]

    coros: list[tuple[str, Any]] = []
    if agency in ("all", "nih"):
        coros.append(("NIH", nih.search(keyword, fiscal_years=[year], limit=limit)))
    if agency in ("all", "nsf"):
        coros.append(("NSF", nsf.search(keyword, year=year, limit=limit)))
    if usa_targets:
        coros.append(("USASpending", usaspending.search(keyword, agencies=usa_targets, year=year, limit=limit)))

    results: list[dict] = []
    for label, coro in coros:
        try:
            results.extend(await coro)
        except Exception as exc:
            errors.append(f"{label} search failed: {exc}")

    # Deduplicate by grant ID
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        if r["grant_id"] not in seen:
            seen.add(r["grant_id"])
            deduped.append(r)
    results = deduped

    # Relevance filter: keyword must appear in title, OR all keyword words in abstract
    keywords = [w.lower() for w in keyword.split() if len(w) > 3]
    if keywords:
        def is_relevant(r: dict) -> bool:
            title = r["title"].lower()
            abstract = (r["abstract"] or "").lower()
            if any(kw in title for kw in keywords):
                return True
            return all(kw in abstract for kw in keywords)

        filtered = [r for r in results if is_relevant(r)]
        removed_count = len(results) - len(filtered)
        if filtered:
            results = filtered
            if removed_count > 0:
                errors.append(
                    f"{removed_count} low-relevance result(s) filtered out "
                    f"(keyword not found in title or abstract)."
                )
        else:
            # Nothing passed — keep all but warn
            errors.append(
                "Relevance filter removed all results — showing unfiltered matches. "
                "Results may be loosely related to your keyword."
            )

    if not results and not errors:
        return f"No grants found for **{keyword}** in {year}."

    total_amount = sum(r["amount"] or 0 for r in results)
    if agency == "all":
        sources = "NIH + NSF + DOE + USDA + NASA + DARPA"
    else:
        sources = agency.upper()
    header = (
        f"## Grant Search: \"{keyword}\" ({year})\n"
        f"Found **{len(results)} grants** across **{sources}** "
        f"totaling **{formatters.fmt_amount(total_amount)}**\n\n"
        f"> _Note: Results are keyword matches from public APIs — "
        f"some may be loosely related to your search term._\n"
    )

    rows = [
        formatters.fmt_grant_row(
            r["title"], r["agency"], r["pi"], r["institution"],
            r["amount"], r["year"], r["abstract"], r["grant_id"],
        )
        for r in results
    ]

    return formatters.fmt_results(header, rows, errors)


# ---------------------------------------------------------------------------
# Tool 2 — get_grant_details
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_grant_details(grant_id: str, agency: str) -> str:
    """
    Retrieve full details for a specific grant by its ID.

    Args:
        grant_id: The grant/project number (e.g. "1R01CA123456-01" for NIH, "2345678" for NSF)
        agency:   Source agency — "nih" or "nsf"
    """
    agency = agency.lower()
    errors: list[str] = []
    results: list[dict] = []

    if agency == "nih":
        try:
            results = await nih.search("", project_num=grant_id, limit=1)
        except Exception as exc:
            errors.append(f"NIH lookup failed: {exc}")
    elif agency == "nsf":
        try:
            results = await nsf.search("", award_id=grant_id, limit=1)
        except Exception as exc:
            errors.append(f"NSF lookup failed: {exc}")
    else:
        return f"Unsupported agency: `{agency}`. Use 'nih' or 'nsf'."

    if not results:
        note = ("\n\n" + "\n".join(f"- {e}" for e in errors)) if errors else ""
        return f"No grant found for ID `{grant_id}` in {agency.upper()}.{note}"

    r = results[0]
    lines = [
        f"## Grant Details: `{r['grant_id']}`",
        f"**Title:** {r['title']}",
        f"**Agency:** {r['agency']}  |  **Fiscal Year:** {r['year']}",
        f"**PI(s):** {r['pi']}",
        f"**Institution:** {r['institution']}",
        f"**Department:** {r.get('department', 'N/A')}",
        f"**Total Award:** {formatters.fmt_amount(r['amount'])}",
        f"**Start Date:** {r.get('start_date', 'N/A')}  |  **End Date:** {r.get('end_date', 'N/A')}",
        f"**Opportunity Number:** {r.get('opportunity_number', 'N/A')}",
        "",
        "### Abstract",
        r.get("abstract") or "_No abstract available_",
    ]

    if r.get("url"):
        lines.append(f"\n**More info:** {r['url']}")

    if errors:
        lines.append("\n**Notes:**")
        lines.extend(f"- {e}" for e in errors)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3 — search_by_pi
# ---------------------------------------------------------------------------
@mcp.tool()
async def search_by_pi(first_name: str, last_name: str) -> str:
    """
    Find all grants awarded to a specific researcher (searches NIH + NSF).

    Args:
        first_name: Researcher's first name
        last_name:  Researcher's last name
    """
    errors: list[str] = []
    results: list[dict] = []

    nih_task = nih.search("", pi_first=first_name, pi_last=last_name, limit=25)
    nsf_task = nsf.search("", pi_first=first_name, pi_last=last_name, limit=25)

    for label, coro in [("NIH", nih_task), ("NSF", nsf_task)]:
        try:
            results.extend(await coro)
        except Exception as exc:
            errors.append(f"{label} search failed: {exc}")

    if not results:
        note = ("\n\n" + "\n".join(f"- {e}" for e in errors)) if errors else ""
        return f"No grants found for **{first_name} {last_name}**.{note}"

    total = sum(r["amount"] or 0 for r in results)
    header = (
        f"## Grants for {first_name} {last_name}\n"
        f"Found **{len(results)} grants** totaling **{formatters.fmt_amount(total)}** "
        f"(NIH + NSF)\n"
    )

    rows = [
        formatters.fmt_grant_row(
            r["title"], r["agency"], r["pi"], r["institution"],
            r["amount"], r["year"], r["abstract"], r["grant_id"],
        )
        for r in results
    ]

    return formatters.fmt_results(header, rows, errors)


# ---------------------------------------------------------------------------
# Tool 4 — search_by_institution
# ---------------------------------------------------------------------------
@mcp.tool()
async def search_by_institution(
    institution_name: str,
    agency: str = "all",
    year: int = 2024,
) -> str:
    """
    Find all grants at a specific university or organization.

    Args:
        institution_name: Name of the institution (e.g. "Johns Hopkins University")
        agency:           Source — "all", "nih", "nsf", "doe", "usda", "nasa", "darpa" (default: "all")
        year:             Fiscal/award year to filter by (default: 2024)
    """
    agency = agency.lower()
    errors: list[str] = []
    results: list[dict] = []

    if agency in ("all", "nih"):
        try:
            results.extend(
                await nih.search("", institution=institution_name, fiscal_years=[year], limit=25)
            )
        except Exception as exc:
            errors.append(f"NIH search failed: {exc}")

    if agency in ("all", "nsf"):
        try:
            results.extend(
                await nsf.search("", institution=institution_name, year=year, limit=25)
            )
        except Exception as exc:
            errors.append(f"NSF search failed: {exc}")

    usa_targets = [a for a in USA_AGENCIES if agency in ("all", a)]
    if usa_targets:
        try:
            results.extend(
                await usaspending.search("", agencies=usa_targets, year=year, institution=institution_name, limit=25)
            )
        except Exception as exc:
            errors.append(f"USASpending search failed: {exc}")

    if not results:
        note = ("\n\n" + "\n".join(f"- {e}" for e in errors)) if errors else ""
        return f"No grants found for **{institution_name}** in {year}.{note}"

    total = sum(r["amount"] or 0 for r in results)
    # Group by department where available
    by_dept: dict[str, list[dict]] = {}
    for r in results:
        dept = r.get("department") or "General"
        by_dept.setdefault(dept, []).append(r)

    header = (
        f"## Grants at {institution_name} ({year})\n"
        f"Found **{len(results)} grants** totaling **{formatters.fmt_amount(total)}** "
        f"across **{len(by_dept)} departments/programs**\n"
    )

    rows = []
    for dept, dept_grants in sorted(by_dept.items()):
        rows.append(f"### {dept}")
        for r in dept_grants:
            rows.append(
                formatters.fmt_grant_row(
                    r["title"], r["agency"], r["pi"], r["institution"],
                    r["amount"], r["year"], r["abstract"], r["grant_id"],
                )
            )

    return formatters.fmt_results(header, rows, errors)


# ---------------------------------------------------------------------------
# Tool 5 — find_open_opportunities
# ---------------------------------------------------------------------------
@mcp.tool()
async def find_open_opportunities(keyword: str, agency: str = "all") -> str:
    """
    Search for currently open funding opportunities from Grants.gov.

    Args:
        keyword: Topic to search for (e.g. "cancer research", "renewable energy")
        agency:  Agency abbreviation to filter by, or "all" (default: "all")
    """
    errors: list[str] = []
    opps: list[dict] = []

    agency_filter = "" if agency.lower() == "all" else agency

    try:
        opps = await grants_gov.search_opportunities(keyword=keyword, agency=agency_filter, limit=15)
    except Exception as exc:
        errors.append(f"Grants.gov search failed: {exc}")

    if not opps:
        note = ("\n\n" + "\n".join(f"- {e}" for e in errors)) if errors else ""
        return f"No open opportunities found for **{keyword}**.{note}"

    header = (
        f"## Open Funding Opportunities: \"{keyword}\"\n"
        f"Found **{len(opps)} active opportunities** on Grants.gov\n"
    )

    rows = [
        formatters.fmt_opportunity_row(
            o["title"],
            o["agency"],
            o["deadline"],
            o["eligibility"],
            o["max_award"],
            o["opportunity_id"],
            o.get("description"),
        )
        for o in opps
    ]

    return formatters.fmt_results(header, rows, errors)


# ---------------------------------------------------------------------------
# Tool 6 — get_funding_trends
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_funding_trends(
    keyword: str,
    start_year: int = 2019,
    end_year: int = 2024,
) -> str:
    """
    Show how funding for a research topic has changed over time (NIH + NSF).

    Args:
        keyword:    Research topic to analyze (e.g. "Alzheimer's disease")
        start_year: First year to include (default: 2019)
        end_year:   Last year to include (default: 2024)
    """
    years = list(range(start_year, end_year + 1))
    errors: list[str] = []
    trend_rows: list[dict] = []

    for year in years:
        row: dict = {
            "year": year,
            "nih_count": 0, "nih_total": 0,
            "nsf_count": 0, "nsf_total": 0,
            "other_count": 0, "other_total": 0,
        }

        try:
            nih_data = await nih.search_by_year(keyword, year)
            row["nih_count"] = nih_data["count"]
            row["nih_total"] = nih_data["total"]
        except Exception as exc:
            errors.append(f"NIH {year}: {exc}")

        try:
            nsf_data = await nsf.search_by_year(keyword, year)
            row["nsf_count"] = nsf_data["count"]
            row["nsf_total"] = nsf_data["total"]
        except Exception as exc:
            errors.append(f"NSF {year}: {exc}")

        try:
            usa_data = await usaspending.search_by_year(
                keyword, year, agencies=list(USA_AGENCIES)
            )
            row["other_count"] = usa_data["count"]
            row["other_total"] = usa_data["total"]
        except Exception as exc:
            errors.append(f"USASpending {year}: {exc}")

        trend_rows.append(row)

    output = formatters.fmt_trends(keyword, trend_rows)

    if errors:
        output += "\n\n**Notes:**\n" + "\n".join(f"- {e}" for e in errors)

    return output


# ---------------------------------------------------------------------------
# ASGI app — FastMCP HTTP app with health route injected
# ---------------------------------------------------------------------------
async def health(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "server": "Grant & Funding Discovery MCP",
            "version": VERSION,
            "status": "ok",
            "tools": TOOLS,
            "sources": ["NIH Reporter v2", "NSF Awards", "Grants.gov"],
        }
    )


# Build the MCP ASGI app then inject the health route
app = mcp.http_app(path="/mcp")
app.routes.insert(0, Route("/", health))

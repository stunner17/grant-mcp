"""Markdown formatting helpers for grant search results."""

from typing import Any


def fmt_amount(amount: int | float | None) -> str:
    if amount is None:
        return "N/A"
    return f"${amount:,.0f}"


def fmt_abstract(text: str | None, limit: int = 300) -> str:
    if not text:
        return "_No abstract available_"
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def fmt_grant_row(
    title: str,
    agency: str,
    pi: str,
    institution: str,
    amount: int | float | None,
    year: int | str | None,
    abstract: str | None,
    grant_id: str,
) -> str:
    lines = [
        f"**{title}**",
        f"- **Agency:** {agency}  |  **ID:** `{grant_id}`",
        f"- **PI:** {pi}  |  **Institution:** {institution}",
        f"- **Amount:** {fmt_amount(amount)}  |  **Year:** {year or 'N/A'}",
        f"- **Abstract:** {fmt_abstract(abstract)}",
    ]
    return "\n".join(lines)


def fmt_opportunity_row(
    title: str,
    agency: str,
    deadline: str,
    eligibility: str,
    max_award: str | None,
    opportunity_id: str,
    description: str | None = None,
) -> str:
    lines = [
        f"**{title}**",
        f"- **Agency:** {agency}  |  **ID:** `{opportunity_id}`",
        f"- **Deadline:** {deadline}  |  **Eligibility:** {eligibility}",
        f"- **Max Award:** {max_award or 'Not specified'}",
    ]
    if description:
        lines.append(f"- **Description:** {fmt_abstract(description)}")
    return "\n".join(lines)


def fmt_results(header: str, rows: list[str], errors: list[str] | None = None) -> str:
    parts = [header, ""]
    if not rows:
        parts.append("_No results found._")
    else:
        parts.append("\n\n---\n\n".join(rows))

    if errors:
        parts.append("\n\n---\n**Notes:**")
        for err in errors:
            parts.append(f"- {err}")

    return "\n".join(parts)


def fmt_trends(keyword: str, rows: list[dict]) -> str:
    if not rows:
        return f"No funding trend data found for **{keyword}**."

    header = f"## Funding Trends: {keyword}\n"
    table_lines = [
        "| Year | NIH | NIH Total | NSF | NSF Total | DOE/USDA/NASA/DARPA | Other Total | Grand Total |",
        "|------|-----|-----------|-----|-----------|---------------------|-------------|-------------|",
    ]
    for row in rows:
        other_count = row.get("other_count", 0)
        other_total = row.get("other_total", 0)
        grand = row["nih_total"] + row["nsf_total"] + other_total
        table_lines.append(
            f"| {row['year']} "
            f"| {row['nih_count']} "
            f"| {fmt_amount(row['nih_total'])} "
            f"| {row['nsf_count']} "
            f"| {fmt_amount(row['nsf_total'])} "
            f"| {other_count} "
            f"| {fmt_amount(other_total)} "
            f"| {fmt_amount(grand)} |"
        )
    return header + "\n".join(table_lines)

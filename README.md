# Grant & Funding Discovery MCP

An MCP (Model Context Protocol) server that lets AI agents search and analyze research grant and funding data from NIH, NSF, DOE, USDA, NASA, DARPA, and Grants.gov using plain-English queries.

## Tools

- **search_grants** — Search awarded grants by keyword, agency, and year.
- **get_grant_details** — Get full details for a specific grant by its ID.
- **search_by_pi** — Find all grants awarded to a specific researcher.
- **search_by_institution** — Find all grants at a specific university or organization.
- **find_open_opportunities** — Search currently open funding opportunities on Grants.gov.
- **get_funding_trends** — Show how funding for a topic has changed over time.

## Data sources

- NIH Reporter v2
- NSF Awards
- Grants.gov
- USASpending.gov (used for DOE, USDA, NASA, and DARPA)

## Using the hosted server

A live instance is already deployed on Render at:

```
https://grant-mcp.onrender.com/mcp
```

Add it to your MCP-compatible client (e.g. Claude Code, Claude Desktop) as a remote/URL-based MCP server pointing at that endpoint — no local install required. A health check is available at the root (`https://grant-mcp.onrender.com/`).

## Running your own instance

To run the server locally or deploy your own copy:

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

This exposes the MCP endpoint at `/mcp` and the health check at `/`. A `render.yaml` is included for one-click deployment to [Render](https://render.com).

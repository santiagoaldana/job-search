> **Session start:** Read `../SHARED_CONTEXT.md` before proceeding. It contains SupplyMind milestones, industry landscape, and ready-to-use content hooks. Use it when drafting LinkedIn posts, outreach scripts, or positioning copy.

# Job Search Orchestration System — CLAUDE.md

## Project Overview

Santiago Aldana's executive job search automation system. 5 Python modules orchestrated via a single CLI entry point (`orchestrate.py`). All modules use the Anthropic API (Claude) for AI enrichment.

**Owner:** Santiago Aldana — MIT Sloan MBA, 20+ yrs FinTech/AI/payments/LATAM leadership. Target roles: C-suite or SVP in payments, embedded banking, Agentic AI, digital identity. Based in Boston, MA.

## Project Structure

```
orchestrate.py          # Single CLI entry point
requirements.txt
.env                    # API keys (never commit)
skills/
  shared.py             # Shared constants, EXECUTIVE_PROFILE, MODEL names, compute_net_score()
  content_intelligence.py   # Module 1: LinkedIn post drafts from FinTech news
  event_discovery.py        # Module 2: Networking event discovery + scoring
  lead_generation.py        # Module 3: C-suite/SVP job openings from job boards
  network_pathfinder.py     # Module 4: Network paths to target company/person + outreach scripts
  cv_synthesis.py           # Module 5: Tailored CV generation from master CV + JD
  email_digest.py           # Weekly event digest email
  scheduler.py              # launchd automation (Monday 8am)
cv/
  contacts_export.csv       # LinkedIn contacts
  output/                   # Generated CV PDFs and HTML
data/
  content_drafts.md
  events_report.md
  leads_report.md
  outreach_scripts.md
  leads_pipeline.json
  events_cache.json
  content_cache.json
  pipeline_summary.md
```

## Runtime Architecture — Read This First

### Source of Truth: Railway (not local)

The live system runs on **Railway** backed by a **Neon PostgreSQL** database. This is the only authoritative data store.

- **Web app (jobsearch service):** `https://jobsearch.aidatasolutions.co` — FastAPI + React frontend
- **MCP server (job-search service):** `https://mcp.aidatasolutions.co` — Starlette SSE server Claude connects to
- **Direct Railway URLs (fallback):** `https://jobsearch-production-4ae1.up.railway.app` and `https://job-search-production-57db.up.railway.app`
- **Local `data/*.json` files** are legacy outputs from the old CLI modules (`orchestrate.py`). The web app does not read or write them. They are stale and not a mirror of anything.
- **Local `jobsearch.db`** (SQLite) is only used when running the app locally without a `DATABASE_URL` env var. It is not synced with Neon.
- When checking contacts, leads, outreach status, or any pipeline data, always query the Railway API or Neon database — not local files.

### Cold Starts

Railway services are always-on — no cold starts for the web app or MCP server. Only **Neon** (free tier) may have a brief 2-3 second wake-up delay after inactivity. This is normal.

### Deploy Policy

Railway auto-deploys from `main`. Always commit and push after code changes — there is no dev/staging instance.

### Local CLI

`orchestrate.py` is a legacy CLI for the old pipeline modules. Run it with the system Python to avoid the `.mcp-venv` conflict:

```bash
/usr/bin/python3 orchestrate.py status
```

The project directory activates `.mcp-venv` (Python 3.12, MCP-only packages) so plain `python3` will fail with missing module errors. Always use `/usr/bin/python3` for the CLI.

## CLI Usage

```bash
/usr/bin/python3 orchestrate.py status
/usr/bin/python3 orchestrate.py content [--days 7] [--drafts 5] [--no-enrich]
/usr/bin/python3 orchestrate.py events [--no-enrich] [--add-url <URL>]
/usr/bin/python3 orchestrate.py leads [--contacts cv/contacts_export.csv] [--no-enrich]
/usr/bin/python3 orchestrate.py network --target "Company" [--contacts ...] [--context ...] [--jd ...] [--person] [--company ...]
/usr/bin/python3 orchestrate.py cv [--jd <url>] [--company <name>] [--role <title>] [--format pdf|html|both]
/usr/bin/python3 orchestrate.py all [--no-enrich] [--contacts ...] [--target ...] [--jd ...] [--company ...] [--role ...]
/usr/bin/python3 orchestrate.py digest
/usr/bin/python3 orchestrate.py schedule install|uninstall|status
```

## Key Conventions

- **All shared state lives in `skills/shared.py`:** paths (BASE_DIR, DATA_DIR, CV_OUTPUT_DIR), EXECUTIVE_PROFILE string, MODEL constants, and `compute_net_score()`.
- **Models:** `MODEL_OPUS` (`claude-opus-4-6`) for generation tasks; `MODEL_HAIKU` (`claude-haiku-4-5-20251001`) for classification/scoring.
- **Net Score formula:** `Utility - (Risk * 0.4)` — used consistently across all modules.
- **`--no-enrich` flag** skips all Claude API calls across every module.
- **Master CV:** `Santiago Aldana 2025-12-09.pdf` in the project root — used by Module 5.

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | All Claude API calls |
| `EVENTBRITE_API_TOKEN` | Optional | Module 2 event discovery |
| `APIFY_API_KEY` | Optional | Module 3 job board scraping |

Set in `.env` file (loaded via `python-dotenv` at startup in `orchestrate.py`).

## Dependencies

Python packages in `requirements.txt`: `anthropic`, `httpx`, `beautifulsoup4`, `feedparser`, `reportlab`, `python-dotenv`, `rich`, `pdfminer.six`.

Install: `pip install -r requirements.txt`

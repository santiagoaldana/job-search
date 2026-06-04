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

## AI Generation Rule — No Anthropic API

**Never use the Anthropic API (`anthropic.AsyncAnthropic()`) for any draft generation in the jobsearch or MCP server.** The Railway backend has no API credits. All AI generation goes through Claude Pro via MCP tools in the Claude Code / Claude Chat session.

For draft generation in the app UI, use one of:
1. **Frontend template** — build the draft directly in the React component from contact/champion data (no backend call needed)
2. **Template-based backend endpoint** — `draft-template`, `draft_followup_from_template` in `outreach_generator.py` (these use no AI)
3. **"Refine in Claude ↗"** — opens Claude.ai with the draft pre-filled for the user to polish manually

Never add new `anthropic.AsyncAnthropic()` calls to backend services. If you find yourself reaching for the Anthropic API to improve draft quality, use option 3 instead.

## Debugging Protocol

The app is in active development and has known instability. When Santiago reports a bug, follow this protocol exactly — no speculation before reading code.

### Bug report format Santiago uses
> "Bug: [what happened]. I used [which button/action] in the app. The contact is [name] at [company]."

### Debug steps (always in this order)
1. Read the relevant router file (`app/routers/`) for the action Santiago used
2. Read the relevant service file (`app/services/`) if the router delegates to one
3. Trace the exact code path — identify the specific lines where logic breaks
4. Check the MCP tool output for the contact/record if the bug involves wrong data
5. Propose a fix with the exact file and line numbers

### Key files for common bug areas
| Bug area | Router | Service |
|---|---|---|
| Daily brief surfacing wrong cards | `app/routers/daily_brief.py` | `app/services/daily_brief.py` |
| Follow-up not marking as sent | `app/routers/outreach.py` (`mark-followup-sent`, `skip`) | — |
| Status not updating after action | `app/routers/outreach.py` (`/response`, `/patch`) | — |
| Draft generation | `app/routers/outreach.py` (`draft-followup`) | `app/services/outreach_generator.py` |
| Gmail sync / reply detection | `app/routers/gmail_sync.py` | `app/services/gmail_sync_service.py` |

### Known structural issues (as of June 2026)
- **Closing message not updating `prior_message`:** When a close is sent through the brief, the `outreach_message` field on the record is not updated to reflect the closing text. The MCP tool `get_outreach_context` then returns stale content.
- **Cards not disappearing immediately after Close out:** UI has a visible delay before re-rendering after `skip` is called. Not a data bug — API response latency before re-render. Expected behavior.

### Known data integrity issue — phantom outreach records
Claude Chat sessions (May 25/27 2026) called `log_outreach` automatically after `quick_add_contact` when Santiago only wanted to save a contact — no outreach had been sent. This started phantom Day 3/7 follow-up clocks on contacts never actually contacted.

**Rule:** NEVER call `log_outreach` or `log_outreach_sent` after `quick_add_contact` unless Santiago explicitly confirms an outreach was already sent. Adding a contact and logging an outreach are two separate actions requiring separate confirmation.

**Fix if it happens again:** Delete the phantom `outreachrecord` row directly via Neon DB (DATABASE_URL is in `.env`). Then the contact will surface naturally via `warm_path` logic in the brief.

### Never do when debugging
- Do not explain a bug before reading the actual record or code
- Do not speculate about what "probably happened" — always verify first
- Do not suggest manual workarounds as the final answer when a code fix is possible

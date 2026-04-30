"""
Job Search MCP Server — expose key actions as Claude tools.

Modes:
  stdio (Claude desktop):   python3 mcp_server.py
  HTTP/SSE (Claude.ai web): python3 mcp_server.py --http [--port 8080]

Env vars:
  MCP_SECRET     — must match MCP_SECRET in FastAPI .env
  API_BASE_URL   — defaults to https://job-search-do1r.onrender.com
"""

import os
import asyncio
import json
import argparse
from typing import Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

API_BASE = os.environ.get("API_BASE_URL", "https://job-search-do1r.onrender.com")
MCP_SECRET = os.environ.get("MCP_SECRET", "")
HEADERS = {"X-MCP-Secret": MCP_SECRET, "Content-Type": "application/json"}

server = Server("job-search")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{API_BASE}{path}", headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()

async def _post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_BASE}{path}", headers=HEADERS, json=body)
        r.raise_for_status()
        return r.json()


# ── Company + contact lookup ──────────────────────────────────────────────────

async def _resolve(company_name: str, contact_name: Optional[str] = None):
    results = await _get("/api/companies", {"q": company_name})
    if not results:
        return None, None, f"'{company_name}' not in funnel — use add_company first."
    company = results[0]
    cid = company["id"]
    contact_id = None
    if contact_name:
        detail = await _get(f"/api/companies/{cid}")
        for c in detail.get("contacts", []):
            if contact_name.lower() in (c.get("name") or "").lower():
                contact_id = c["id"]
                break
    return cid, contact_id, f"Resolved: {company['name']} (id={cid})"


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="quick_add_contact",
            description="Add a contact met at a conference or event. Automatically matches the company against Santiago's funnel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "company_name": {"type": "string"},
                    "met_via": {"type": "string", "description": "e.g. 'MIT FinTech Summit panel'"},
                    "linkedin_url": {"type": "string"},
                    "relationship_notes": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="generate_outreach",
            description="Draft a short outreach email (≤75 words, Dalton method). Use email_type='event_met' right after meeting someone.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "contact_name": {"type": "string"},
                    "context": {"type": "string"},
                    "ask": {"type": "string"},
                    "hook": {"type": "string"},
                    "email_type": {"type": "string", "enum": ["cold", "event_met", "followup"]},
                },
                "required": ["company_name"],
            },
        ),
        types.Tool(
            name="compose_linkedin_post",
            description="Generate a LinkedIn post in Santiago's executive voice from a topic or conference insight.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "e.g. 'AI fraud detection is shifting from rules to behavioral graphs — takeaway from FinTech Summit'",
                    },
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="get_daily_brief",
            description="Get today's priority actions: follow-ups due, hot leads, upcoming events.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_hot_leads",
            description="List active job leads with fit score ≥ 65 and Boston-compatible location.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="search_companies",
            description="Search Santiago's funnel by company name.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        types.Tool(
            name="add_company",
            description="Add a new company to Santiago's job search funnel at 'pool' stage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "funding_stage": {
                        "type": "string",
                        "enum": ["series_b", "series_c", "series_d", "public", "unknown"],
                    },
                    "motivation": {"type": "integer", "minimum": 1, "maximum": 10},
                    "career_page_url": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="add_event",
            description="Add a networking event to Santiago's tracker.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "location": {"type": "string"},
                    "url": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["strategic", "networking", "conference", "meetup"],
                    },
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="log_outreach_sent",
            description="Log that Santiago sent an outreach email to a company. Call this right after sending so the 3/7 day follow-up reminders are scheduled automatically.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "contact_name": {"type": "string", "description": "Name of person emailed (optional)"},
                    "subject": {"type": "string"},
                    "body": {"type": "string", "description": "Email body text (optional but recommended for follow-up context)"},
                    "channel": {"type": "string", "enum": ["email", "linkedin"], "description": "Default: email"},
                },
                "required": ["company_name", "subject"],
            },
        ),
        types.Tool(
            name="draft_followup",
            description="Draft a Day 3 bump or Day 7 close for a pending outreach. Returns the subject and body ready to copy-paste. Use when a follow-up is due.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "followup_day": {"type": "integer", "enum": [3, 7], "description": "3 for soft bump, 7 for polite close"},
                    "language": {"type": "string", "enum": ["en", "es"], "description": "Email language. Default: en"},
                },
                "required": ["company_name", "followup_day"],
            },
        ),
    ]


# ── Tool dispatch ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except httpx.HTTPStatusError as e:
        err = {"error": f"API {e.response.status_code}", "detail": e.response.text[:300]}
        return [types.TextContent(type="text", text=json.dumps(err))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _dispatch(name: str, args: dict) -> dict:
    if name == "quick_add_contact":
        return await _post("/api/contacts/quick-add", {
            "name": args["name"],
            "title": args.get("title"),
            "company_name": args.get("company_name"),
            "met_via": args.get("met_via"),
            "linkedin_url": args.get("linkedin_url"),
            "relationship_notes": args.get("relationship_notes"),
        })

    elif name == "generate_outreach":
        cid, contact_id, status = await _resolve(args["company_name"], args.get("contact_name"))
        if cid is None:
            return {"error": status}
        return await _post("/api/outreach/generate", {
            "company_id": cid,
            "contact_id": contact_id,
            "context": args.get("context"),
            "hook": args.get("hook"),
            "ask": args.get("ask"),
            "email_type": args.get("email_type", "cold"),
        })

    elif name == "compose_linkedin_post":
        return await _post("/api/content/compose", {"context": args["topic"]})

    elif name == "get_daily_brief":
        return await _get("/api/daily-brief")

    elif name == "list_hot_leads":
        return await _get("/api/leads/hot")

    elif name == "search_companies":
        return await _get("/api/companies", {"q": args["query"]})

    elif name == "add_company":
        return await _post("/api/companies", {
            "name": args["name"],
            "funding_stage": args.get("funding_stage", "unknown"),
            "motivation": args.get("motivation", 7),
            "career_page_url": args.get("career_page_url"),
        })

    elif name == "add_event":
        return await _post("/api/events", {
            "name": args["name"],
            "date": args.get("date"),
            "location": args.get("location"),
            "url": args.get("url"),
            "description": args.get("description"),
            "category": args.get("category", "strategic"),
        })

    elif name == "log_outreach_sent":
        cid, contact_id, status = await _resolve(args["company_name"], args.get("contact_name"))
        if cid is None:
            return {"error": status}
        return await _post("/api/outreach", {
            "company_id": cid,
            "contact_id": contact_id,
            "channel": args.get("channel", "email"),
            "subject": args["subject"],
            "body": args.get("body"),
        })

    elif name == "draft_followup":
        # Find the most recent pending outreach record for this company
        cid, _, status = await _resolve(args["company_name"])
        if cid is None:
            return {"error": status}
        records = await _get("/api/outreach", {"company_id": cid})
        if not records:
            return {"error": f"No outreach records found for {args['company_name']}"}
        # Pick the most recent pending one
        pending = [r for r in records if r.get("response_status") == "pending"]
        if not pending:
            return {"error": f"No pending outreach found for {args['company_name']}"}
        record_id = pending[0]["id"]
        return await _post(f"/api/outreach/{record_id}/draft-followup", {
            "followup_day": args["followup_day"],
            "language": args.get("language", "en"),
        })

    return {"error": f"Unknown tool: {name}"}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Job Search MCP Server")
    parser.add_argument("--http", action="store_true", help="Run as HTTP/SSE server (for Claude.ai web/mobile)")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP mode (default 8080)")
    parser.add_argument("--messages-path", default="/messages/", help="Path prefix for POST messages endpoint")
    a = parser.parse_args()

    if a.http:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        from starlette.responses import JSONResponse
        from starlette.background import BackgroundTask
        import uvicorn
        import threading

        messages_path = a.messages_path
        sse = SseServerTransport(messages_path)

        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())

        async def health(request):
            return JSONResponse({"status": "ok"})

        def _keep_alive():
            """Ping self every 4 minutes to prevent Render free-tier cold start."""
            import time
            import urllib.request
            port = a.port
            url = f"http://localhost:{port}/health"
            while True:
                time.sleep(240)
                try:
                    urllib.request.urlopen(url, timeout=10)
                except Exception:
                    pass

        t = threading.Thread(target=_keep_alive, daemon=True)
        t.start()

        starlette_app = Starlette(routes=[
            Route("/health", endpoint=health),
            Route("/sse", endpoint=handle_sse),
            Mount(messages_path, app=sse.handle_post_message),
        ])
        uvicorn.run(starlette_app, host="0.0.0.0", port=a.port)
    else:
        async def _run_stdio():
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream, server.create_initialization_options())
        asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()

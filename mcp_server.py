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

async def _patch(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.patch(f"{API_BASE}{path}", headers=HEADERS, json=body)
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
            name="get_ghosted_outreach",
            description="List contacts that were ghosted (no response after both follow-ups). Shows who to re-engage or close out.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_outreach_pipeline",
            description="Get all active outreach records with contact/company info, follow-up status, and days since sent. Use this to generate an outreach pipeline artifact showing who is in process.",
            inputSchema={"type": "object", "properties": {}},
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
        types.Tool(
            name="get_contact_next_step",
            description="Get the recommended next outreach action for a specific contact. Returns whether to draft an email, LinkedIn DM, or connection request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {"type": "string", "description": "Full or partial name of the contact"},
                    "company_name": {"type": "string", "description": "Company name to narrow the search (optional)"},
                },
                "required": ["contact_name"],
            },
        ),
        types.Tool(
            name="draft_linkedin_message",
            description="Draft a LinkedIn DM or connection request for a contact. Use message_type='linkedin_dm' for 1st-degree connections, 'connection_request' for others (randomly assigns A/B variant).",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {"type": "string"},
                    "company_name": {"type": "string"},
                    "message_type": {
                        "type": "string",
                        "enum": ["linkedin_dm", "connection_request"],
                        "description": "linkedin_dm for 1st-degree, connection_request for 2nd/3rd degree",
                    },
                    "context": {"type": "string", "description": "Additional context (prior email sent, event met at, etc.)"},
                },
                "required": ["contact_name", "message_type"],
            },
        ),
        types.Tool(
            name="mark_linkedin_status",
            description="Record a LinkedIn action taken for a contact: request_sent, accepted (connection accepted → now 1st-degree), or dm_sent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {"type": "string"},
                    "company_name": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["request_sent", "accepted", "dm_sent"],
                    },
                },
                "required": ["contact_name", "status"],
            },
        ),
        types.Tool(
            name="mark_email_bounced",
            description="Mark a contact's email as bounced. Advances to the next pattern guess and returns the new recommended action.",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_name": {"type": "string"},
                    "company_name": {"type": "string"},
                },
                "required": ["contact_name"],
            },
        ),
        types.Tool(
            name="get_progress_report",
            description="Get a visual job search health report showing pipeline velocity, outreach funnel, follow-up health, and contact gaps. Returns an HTML artifact.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_outreach_stats",
            description="Get outreach effectiveness stats: response rates by channel (email/linkedin/referral), ghosted %, avg days to reply, and best performing channel. Returns an HTML artifact.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="schedule_linkedin_post",
            description="Schedule a LinkedIn post for the next optimal slot (Wed/Thu 3-5 PM ET). Provide the draft_id from the Content page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "integer", "description": "ID of the ContentDraft to schedule"},
                },
                "required": ["draft_id"],
            },
        ),
        types.Tool(
            name="get_references",
            description="List people who can vouch for Santiago at a target company. Useful before an interview to know who to call on. Optionally filter by company name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "Filter by target company name (optional)"},
                },
            },
        ),
        types.Tool(
            name="generate_substack_draft",
            description="Generate a Substack newsletter article (600-1000 words) in Santiago's executive voice. Returns the full draft for review in the Content > Substack tab.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Newsletter topic, e.g. 'How AI is reshaping executive hiring in FinTech'"},
                },
                "required": ["topic"],
            },
        ),
        types.Tool(
            name="find_contacts",
            description="Find hiring manager contacts for a company using Crunchbase, Apollo, LinkedIn, and other sources. Saves new contacts to the funnel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                },
                "required": ["company_name"],
            },
        ),
    ]


# ── HTML renderers ────────────────────────────────────────────────────────────

def _render_outreach_stats_html(data: dict) -> str:
    def pct(v):
        if v is None: return "—"
        return f"{round(v * 100)}%"

    channels = ["email", "linkedin", "referral"]
    channel_rows = ""
    for ch in channels:
        d = data.get("by_channel", {}).get(ch, {"sent": 0, "response_rate": 0, "ghosted_pct": 0})
        channel_rows += f"""
        <tr style="border-top:1px solid #e8e0d8">
          <td style="padding:6px 0;text-transform:capitalize;color:#1c1917">{ch}</td>
          <td style="padding:6px 0;text-align:right;color:#6b7280">{d['sent']}</td>
          <td style="padding:6px 0;text-align:right;color:#16a34a">{pct(d.get('response_rate'))}</td>
          <td style="padding:6px 0;text-align:right;color:#6b7280">{pct(d.get('ghosted_pct'))}</td>
        </tr>"""

    best = data.get("best_channel")
    best_html = ""
    if best:
        best_rate = pct(data.get("by_channel", {}).get(best, {}).get("response_rate"))
        best_html = f'<p style="margin:8px 0 0;font-size:13px;color:#6b7280">Best channel: <strong style="color:#c96442;text-transform:capitalize">{best}</strong> ({best_rate} response rate)</p>'

    avg = data.get("avg_days_to_positive")
    avg_str = f"{avg}d" if avg is not None else "—"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body{{margin:0;padding:16px;background:#f5f0eb;font-family:system-ui,sans-serif;color:#1c1917}}
  .card{{background:#fff;border:1px solid #e8e0d8;border-radius:12px;padding:16px;margin-bottom:12px}}
  .title{{font-size:13px;font-weight:600;color:#c96442;margin:0 0 12px}}
  .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:10px}}
  .grid2{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:10px}}
  .stat{{background:#faf7f4;border-radius:8px;padding:10px;text-align:center}}
  .stat-val{{font-size:20px;font-weight:700;color:#1c1917}}
  .stat-label{{font-size:11px;color:#78716c;margin-top:2px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;color:#78716c;font-weight:500;padding:4px 0;font-size:12px}}
  th:not(:first-child){{text-align:right}}
</style></head><body>
<h2 style="margin:0 0 12px;font-size:17px;color:#1c1917">Outreach Effectiveness</h2>
<p style="margin:0 0 16px;font-size:12px;color:#78716c">All-time stats · {data.get('total_sent',0)} outreach records</p>

<div class="card">
  <p class="title">Summary</p>
  <div class="grid">
    <div class="stat"><div class="stat-val">{data.get('total_sent',0)}</div><div class="stat-label">Total sent</div></div>
    <div class="stat"><div class="stat-val">{data.get('sent_last_30d',0)}</div><div class="stat-label">Last 30 days</div></div>
    <div class="stat"><div class="stat-val" style="color:#16a34a">{pct(data.get('overall_response_rate'))}</div><div class="stat-label">Response rate</div></div>
  </div>
  <div class="grid2">
    <div class="stat"><div class="stat-val" style="color:#6b7280">{pct(data.get('overall_ghosted_pct'))}</div><div class="stat-label">Ghosted</div></div>
    <div class="stat"><div class="stat-val">{avg_str}</div><div class="stat-label">Avg days to reply</div></div>
  </div>
  {best_html}
</div>

<div class="card">
  <p class="title">By Channel</p>
  <table>
    <thead><tr>
      <th>Channel</th><th style="text-align:right">Sent</th>
      <th style="text-align:right">Response</th><th style="text-align:right">Ghosted</th>
    </tr></thead>
    <tbody>{channel_rows}</tbody>
  </table>
</div>
</body></html>"""


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

    elif name == "get_ghosted_outreach":
        records = await _get("/api/outreach", {"response_status": "ghosted"})
        companies = await _get("/api/companies", {"active_only": False})
        company_map = {c["id"]: c["name"] for c in companies}
        contact_ids = list({r["contact_id"] for r in records if r.get("contact_id")})
        contact_map = {}
        for cid in contact_ids:
            try:
                c = await _get(f"/api/contacts/{cid}")
                contact_map[cid] = {"name": c.get("name", ""), "title": c.get("title", "")}
            except Exception:
                pass
        from datetime import date
        today = date.today()
        result = []
        seen = set()
        for r in records:
            key = (r["company_id"], r["contact_id"])
            if key in seen:
                continue
            seen.add(key)
            sent = r.get("sent_at", "")[:10]
            days_since = (today - date.fromisoformat(sent)).days if sent else None
            contact_info = contact_map.get(r.get("contact_id"), {})
            result.append({
                "contact_name": contact_info.get("name", "—"),
                "contact_title": contact_info.get("title", ""),
                "company": company_map.get(r["company_id"], f"Company #{r['company_id']}"),
                "subject": r.get("subject", ""),
                "sent_date": sent,
                "days_since": days_since,
                "record_id": r["id"],
            })
        return {"ghosted": result, "total": len(result), "today": str(today)}

    elif name == "get_outreach_pipeline":
        records = await _get("/api/outreach")
        companies = await _get("/api/companies", {"active_only": False})
        company_map = {c["id"]: c["name"] for c in companies}

        # Fetch unique contact names in parallel
        contact_ids = list({r["contact_id"] for r in records if r.get("contact_id")})
        contact_map = {}
        for cid in contact_ids:
            try:
                c = await _get(f"/api/contacts/{cid}")
                contact_map[cid] = {"name": c.get("name", ""), "title": c.get("title", "")}
            except Exception:
                pass

        from datetime import date
        today = date.today()
        pipeline = []
        seen_company_contact = set()
        for r in records:
            key = (r["company_id"], r["contact_id"])
            if key in seen_company_contact:
                continue
            seen_company_contact.add(key)
            sent = r.get("sent_at", "")[:10]
            days_since = (today - date.fromisoformat(sent)).days if sent else None
            f3_due = r.get("follow_up_3_due", "")
            f7_due = r.get("follow_up_7_due", "")
            f3_sent = r.get("follow_up_3_sent", False)
            f7_sent = r.get("follow_up_7_sent", False)
            if not f3_sent and f3_due and f3_due <= str(today):
                next_action = f"Day 3 bump due ({f3_due})"
            elif not f7_sent and f7_due and f7_due <= str(today):
                next_action = f"Day 7 close due ({f7_due})"
            elif not f3_sent:
                next_action = f"Day 3 bump on {f3_due}"
            elif not f7_sent:
                next_action = f"Day 7 close on {f7_due}"
            else:
                next_action = "All follow-ups sent"
            contact_info = contact_map.get(r.get("contact_id"), {})
            pipeline.append({
                "contact_name": contact_info.get("name", "—"),
                "contact_title": contact_info.get("title", ""),
                "company": company_map.get(r["company_id"], f"Company #{r['company_id']}"),
                "subject": r.get("subject", ""),
                "sent_date": sent,
                "days_since": days_since,
                "status": r.get("response_status", "pending"),
                "next_action": next_action,
                "notes": r.get("notes", ""),
                "record_id": r["id"],
            })
        return {"pipeline": pipeline, "total": len(pipeline), "today": str(today)}

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

    elif name == "get_contact_next_step":
        # Find contact by name
        contacts = await _get("/api/contacts")
        name_lower = args["contact_name"].lower()
        company_filter = args.get("company_name", "").lower()
        matches = [
            c for c in contacts
            if name_lower in (c.get("name") or "").lower()
            and (not company_filter or company_filter in (c.get("company_name") or "").lower())
        ]
        if not matches:
            return {"error": f"No contact found matching '{args['contact_name']}'"}
        contact = matches[0]
        return await _get(f"/api/contacts/{contact['id']}/next-step")

    elif name == "draft_linkedin_message":
        contacts = await _get("/api/contacts")
        name_lower = args["contact_name"].lower()
        company_filter = args.get("company_name", "").lower()
        matches = [
            c for c in contacts
            if name_lower in (c.get("name") or "").lower()
            and (not company_filter or company_filter in (c.get("company_name") or "").lower())
        ]
        if not matches:
            return {"error": f"No contact found matching '{args['contact_name']}'"}
        contact_row = matches[0]

        # Resolve company
        company_name = contact_row.get("company_name") or args.get("company_name", "")
        cid, contact_id, status = await _resolve(company_name, args["contact_name"])
        if cid is None:
            return {"error": status}

        # Choose A/B variant for connection requests
        import random
        msg_type = args["message_type"]
        if msg_type == "connection_request":
            email_type = random.choice(["connection_request_a", "connection_request_b"])
        else:
            email_type = "linkedin_dm"

        result = await _post("/api/outreach/generate", {
            "company_id": cid,
            "contact_id": contact_id,
            "context": args.get("context"),
            "email_type": email_type,
        })

        # Store the variant on the contact if it was a connection request
        if msg_type == "connection_request":
            variant = "A" if email_type == "connection_request_a" else "B"
            try:
                await _patch(f"/api/contacts/{contact_row['id']}", {"connection_request_variant": variant})
            except Exception:
                pass
            result["variant"] = variant
            result["message_type"] = "connection_request"
        else:
            result["message_type"] = "linkedin_dm"

        return result

    elif name == "mark_linkedin_status":
        contacts = await _get("/api/contacts")
        name_lower = args["contact_name"].lower()
        company_filter = args.get("company_name", "").lower()
        matches = [
            c for c in contacts
            if name_lower in (c.get("name") or "").lower()
            and (not company_filter or company_filter in (c.get("company_name") or "").lower())
        ]
        if not matches:
            return {"error": f"No contact found matching '{args['contact_name']}'"}
        contact_row = matches[0]
        contact_id = contact_row["id"]

        status = args["status"]
        update = {}
        if status == "request_sent":
            update["outreach_status"] = "connection_requested"
        elif status == "accepted":
            update["connection_degree"] = 1
            update["outreach_status"] = "none"  # reset so next-step logic runs fresh
        elif status == "dm_sent":
            update["outreach_status"] = "linkedin_dm"

        result = await _patch(f"/api/contacts/{contact_id}", update)
        return {"ok": True, "contact": contact_row["name"], "status_recorded": status, "contact_id": contact_id}

    elif name == "mark_email_bounced":
        contacts = await _get("/api/contacts")
        name_lower = args["contact_name"].lower()
        company_filter = args.get("company_name", "").lower()
        matches = [
            c for c in contacts
            if name_lower in (c.get("name") or "").lower()
            and (not company_filter or company_filter in (c.get("company_name") or "").lower())
        ]
        if not matches:
            return {"error": f"No contact found matching '{args['contact_name']}'"}
        contact_row = matches[0]
        return await _post(f"/api/contacts/{contact_row['id']}/bounce", {})

    elif name == "get_progress_report":
        data = await _get("/api/reports/progress")
        from app.services.progress_report import render_progress_html
        html = render_progress_html(data)
        return {"type": "html", "html": html, "data": data}

    elif name == "get_outreach_stats":
        data = await _get("/api/outreach/stats")
        html = _render_outreach_stats_html(data)
        return {"type": "html", "html": html, "data": data}

    elif name == "schedule_linkedin_post":
        slot = await _get("/api/content/linkedin/next-slot")
        scheduled_at = slot.get("slot_iso") or slot.get("next_slot") or slot.get("scheduled_at")
        if not scheduled_at:
            return {"error": "Could not determine next slot", "slot_response": slot}
        result = await _patch(f"/api/content/{args['draft_id']}", {"status": "scheduled", "scheduled_at": scheduled_at})
        slot_label = slot.get("label") or slot.get("slot_label") or scheduled_at[:16]
        return {"draft_id": args["draft_id"], "scheduled_at": scheduled_at, "message": f"Scheduled for {slot_label}"}

    elif name == "get_references":
        company_name = args.get("company_name")
        if company_name:
            cid, _, status = await _resolve(company_name)
            if cid is None:
                return {"error": status}
            refs = await _get(f"/api/references/for-company/{cid}")
        else:
            refs = await _get("/api/references")
        if not refs:
            return {"references": [], "message": "No references found"}
        lines = []
        for r in refs:
            strength = r.get("strength", "medium")
            name = r.get("contact_name", "Unknown")
            title = r.get("contact_title", "")
            rel = r.get("relationship", "")
            roles = r.get("role_types", "")
            lines.append(f"• [{strength.upper()}] {name}" + (f" — {title}" if title else "") +
                         (f"\n  Relationship: {rel}" if rel else "") +
                         (f"\n  Good for: {roles}" if roles else ""))
        return {"references": refs, "summary": "\n".join(lines)}

    elif name == "generate_substack_draft":
        result = await _post("/api/content/substack/generate", {"topic": args["topic"], "count": 1})
        drafts = result.get("drafts", [])
        if not drafts:
            return {"error": "No draft generated"}
        draft = drafts[0]
        word_count = len(draft.get("body", "").split())
        return {
            "id": draft.get("id"),
            "word_count": word_count,
            "net_score": draft.get("net_score"),
            "body": draft.get("body", ""),
            "status": "pending — review in Content → Substack tab",
        }

    elif name == "find_contacts":
        cid, _, status = await _resolve(args["company_name"])
        if cid is None:
            return {"error": status}
        result = await _post(f"/api/companies/{cid}/find-contacts", {})
        return result

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

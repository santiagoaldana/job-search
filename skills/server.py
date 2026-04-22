"""
Web Dashboard Server — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Local Flask server that replaces all terminal commands with a browser UI.

Start:  python3 orchestrate.py server
Open:   http://localhost:5050

API endpoints (all JSON):
  GET  /api/dashboard        — pulse + actions + lamp + events (full brief)
  GET  /api/drafts           — pending drafts list
  POST /api/drafts/<id>/approve  — approve + send a draft via Gmail
  POST /api/drafts/<id>/skip     — skip a draft (keeps pending)
  POST /api/drafts/<id>/delete   — delete a draft
  POST /api/drafts/<id>/edit     — update subject/body before sending
  GET  /api/tracker          — full outreach tracker
  POST /api/tracker/add      — quick-add a new contact
  POST /api/tracker/respond  — mark contact as responded/booster
  GET  /api/lamp             — full LAMP list (sorted)
  POST /api/lamp/motivation  — update motivation scores
  GET  /api/events           — upcoming events
  GET  /api/leads            — leads pipeline
  POST /api/scan             — trigger gmail scan (background)
  GET  /api/scan/status      — last scan result
"""

import json
import os
import threading
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__, static_folder=str(Path(__file__).parent / "web"))

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# ── Shared state ──────────────────────────────────────────────────────────────
_scan_status    = {"running": False, "last_result": None, "last_run": None}
_li_scan_status = {"running": False, "last_result": None, "last_run": None}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(filename: str):
    p = DATA_DIR / filename
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _gmail_service():
    """Get authenticated Gmail service for GMAIL_ACCOUNT_1."""
    from skills.gmail_monitor import authenticate_gmail, _init_paths
    _init_paths()
    account = os.environ.get("GMAIL_ACCOUNT_1", "")
    if not account:
        raise RuntimeError("GMAIL_ACCOUNT_1 not set in .env")
    return authenticate_gmail(account), account


# ── Static UI ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ── Dashboard API ─────────────────────────────────────────────────────────────

@app.route("/api/dashboard")
def api_dashboard():
    tracker = _load("outreach_tracker.json")
    lamp    = _load("lamp_list.json")
    drafts  = _load("pending_drafts.json")
    events  = _load("events_cache.json")

    today = date.today()

    # ── Pulse ──────────────────────────────────────────────────────────────
    active    = [r for r in tracker if not r.get("low_priority")]
    boosters  = sum(1 for r in active if r.get("status") == "booster")
    responded = sum(1 for r in active if r.get("status") in ("responded", "booster", "obligate"))
    waiting   = sum(1 for r in active if r.get("status") == "sent")
    pending_drafts = sum(1 for d in drafts if d.get("status") == "pending")

    overdue_count = 0
    for r in active:
        if r.get("status") == "sent":
            for field in ("follow_up_due", "second_contact_due"):
                due_str = r.get(field, "")
                if due_str:
                    try:
                        if date.fromisoformat(due_str) <= today:
                            overdue_count += 1
                            break
                    except ValueError:
                        pass

    pulse = {
        "boosters": boosters,
        "responded": responded,
        "waiting": waiting,
        "pending_drafts": pending_drafts,
        "overdue": overdue_count,
        "booster_target": 6,
        "date": today.strftime("%A, %B %-d %Y"),
    }

    # ── Actions ────────────────────────────────────────────────────────────
    actions = []
    for r in active:
        company = r.get("company", "")
        contact = r.get("contact_name", "")
        status  = r.get("status", "")

        if status == "sent":
            for field, label, instruction in [
                ("follow_up_due", "Day-3",
                 f"Find a 2nd contact at {company} and send the same email in parallel"),
                ("second_contact_due", "Day-7",
                 f"Re-send to {contact} via a different channel (used: {r.get('channel','email')})"),
            ]:
                due_str = r.get(field, "")
                if not due_str:
                    continue
                try:
                    due = date.fromisoformat(due_str)
                except ValueError:
                    continue
                days_diff = (today - due).days
                if days_diff >= 0:
                    actions.append({
                        "overdue": days_diff > 0,
                        "days_diff": days_diff,
                        "due": due_str,
                        "label": label,
                        "company": company,
                        "contact": contact,
                        "contact_role": r.get("contact_role", ""),
                        "channel": r.get("channel", "email"),
                        "instruction": instruction,
                    })

        elif status == "responded":
            last = r.get("last_contact_date") or r.get("sent_date", "")
            if last and not r.get("referral_received"):
                try:
                    last_dt = date.fromisoformat(last[:10])
                    elapsed = (today - last_dt).days
                    if elapsed >= 30:
                        actions.append({
                            "overdue": elapsed > 35,
                            "days_diff": elapsed - 30,
                            "due": (last_dt + timedelta(days=30)).isoformat(),
                            "label": "Harvest",
                            "company": company,
                            "contact": contact,
                            "contact_role": r.get("contact_role", ""),
                            "channel": r.get("channel", "email"),
                            "instruction": f"Monthly check-in with {contact} — share something useful, stay top-of-mind",
                        })
                except ValueError:
                    pass

    actions.sort(key=lambda a: (-a["days_diff"], a["due"]))

    # ── LAMP top 10 ────────────────────────────────────────────────────────
    tracker_status = {}
    for r in active:
        co = r.get("company", "").lower().strip()
        st = r.get("status", "")
        priority = {"booster": 4, "responded": 3, "obligate": 3, "sent": 2}
        if co not in tracker_status or priority.get(st, 0) > priority.get(tracker_status[co], 0):
            tracker_status[co] = st

    if isinstance(lamp, dict):
        lamp = list(lamp.values())
    sorted_lamp = sorted(lamp, key=lambda e: (-e.get("motivation", 5), -e.get("lamp_score", 0)))
    warm  = [e for e in sorted_lamp if e.get("contacts")][:10]
    build = [e for e in sorted_lamp if not e.get("contacts") and e.get("motivation", 5) >= 7][:8]

    lamp_top = []
    for e in warm:
        co = e.get("company", "")
        actual_status = tracker_status.get(co.lower().strip(), e.get("status", "not_started"))
        lamp_top.append({
            "company":  co,
            "motivation": e.get("motivation", 5),
            "lamp_score": e.get("lamp_score", 0),
            "contacts": e.get("contacts", []),
            "open_roles": e.get("open_roles", []),
            "status": actual_status,
            "lamp_status": e.get("status", "not_started"),
            "notes": e.get("notes", ""),
        })

    lamp_build = [{"company": e.get("company", ""), "motivation": e.get("motivation", 5)} for e in build]

    # ── Events next 14 days ────────────────────────────────────────────────
    cutoff = today + timedelta(days=14)
    upcoming = []
    for e in events:
        date_str = e.get("date", "")
        if not date_str or date_str.lower() in ("tbd", "recurring", "various"):
            continue
        try:
            ev_date = date.fromisoformat(date_str[:10])
        except ValueError:
            continue
        if today <= ev_date <= cutoff:
            category  = e.get("category", "")
            net_score = e.get("net_score", 0)
            if category in ("STRATEGIC", "HIGH_PROBABILITY") or net_score >= 5:
                days_away = (ev_date - today).days
                upcoming.append({
                    "name":      e.get("name", ""),
                    "date":      date_str,
                    "date_label": "Today" if days_away == 0 else ("Tomorrow" if days_away == 1 else ev_date.strftime("%b %-d")),
                    "location":  e.get("location", ""),
                    "url":       e.get("url", ""),
                    "category":  category,
                    "net_score": net_score,
                    "days_away": days_away,
                    "urgent":    days_away <= 7,
                })
    upcoming.sort(key=lambda x: (-x["net_score"], x["days_away"]))
    upcoming = upcoming[:8]

    return jsonify({
        "pulse":   pulse,
        "actions": actions,
        "lamp":    lamp_top,
        "build":   lamp_build,
        "events":  upcoming,
        "scan":    _scan_status,
    })


# ── Drafts API ────────────────────────────────────────────────────────────────

@app.route("/api/drafts")
def api_drafts():
    drafts  = _load("pending_drafts.json")
    pending = [d for d in drafts if d.get("status") == "pending"]
    pending.sort(key=lambda d: d.get("days_elapsed", 0), reverse=True)
    return jsonify({"drafts": pending, "total": len(pending)})


@app.route("/api/drafts/<draft_id>/approve", methods=["POST"])
def api_draft_approve(draft_id):
    from skills.gmail_monitor import load_pending_drafts, save_pending_drafts, send_via_gmail
    drafts = load_pending_drafts()

    draft = next((d for d in drafts if d.get("draft_id") == draft_id), None)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404

    to_email = draft.get("contact_email", "")
    if not to_email:
        return jsonify({"error": "No email address on this contact — edit the draft to add one"}), 400

    try:
        service, from_account = _gmail_service()
        sent_id = send_via_gmail(
            service,
            to_email=to_email,
            subject=draft.get("subject", ""),
            body=draft.get("body", ""),
            from_email=from_account,
            thread_id=draft.get("thread_id", ""),
        )
        draft["status"] = "sent"
        draft["sent_at"] = datetime.now().isoformat()
        draft["gmail_id"] = sent_id
        save_pending_drafts(drafts)
        return jsonify({"ok": True, "sent_id": sent_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/drafts/<draft_id>/edit", methods=["POST"])
def api_draft_edit(draft_id):
    from skills.gmail_monitor import load_pending_drafts, save_pending_drafts
    data = request.get_json()
    drafts = load_pending_drafts()

    draft = next((d for d in drafts if d.get("draft_id") == draft_id), None)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404

    if "subject" in data:
        draft["subject"] = data["subject"]
    if "body" in data:
        draft["body"] = data["body"]
        draft["word_count"] = len(data["body"].split())
    if "contact_email" in data:
        draft["contact_email"] = data["contact_email"]

    save_pending_drafts(drafts)
    return jsonify({"ok": True, "draft": draft})


@app.route("/api/drafts/<draft_id>/skip", methods=["POST"])
def api_draft_skip(draft_id):
    # Skip = leave as pending (no-op, just confirm)
    return jsonify({"ok": True})


@app.route("/api/drafts/<draft_id>/delete", methods=["POST"])
def api_draft_delete(draft_id):
    from skills.gmail_monitor import load_pending_drafts, save_pending_drafts
    drafts = load_pending_drafts()
    before = len(drafts)
    drafts = [d for d in drafts if d.get("draft_id") != draft_id]
    save_pending_drafts(drafts)
    return jsonify({"ok": True, "removed": before - len(drafts)})


# ── Tracker API ───────────────────────────────────────────────────────────────

@app.route("/api/tracker")
def api_tracker():
    tracker = _load("outreach_tracker.json")
    active  = [r for r in tracker if not r.get("low_priority")]
    active.sort(key=lambda r: r.get("sent_date", ""), reverse=True)
    return jsonify({"records": active, "total": len(tracker)})


@app.route("/api/tracker/add", methods=["POST"])
def api_tracker_add():
    from skills.outreach_tracker import load_tracker, save_tracker, add_outreach
    data = request.get_json()

    required = ["company", "contact_name", "contact_role"]
    for f in required:
        if not data.get(f, "").strip():
            return jsonify({"error": f"{f} is required"}), 400

    records = load_tracker()
    record  = add_outreach(
        records,
        company       = data["company"].strip(),
        contact_name  = data["contact_name"].strip(),
        contact_role  = data["contact_role"].strip(),
        channel       = data.get("channel", "email"),
        contact_email = data.get("contact_email", ""),
    )
    if data.get("notes"):
        record.notes = data["notes"]
    save_tracker(records)
    return jsonify({"ok": True, "record": asdict(record)})


@app.route("/api/tracker/respond", methods=["POST"])
def api_tracker_respond():
    from skills.outreach_tracker import load_tracker, save_tracker, mark_responded
    data    = request.get_json()
    company = data.get("company", "").strip()
    contact = data.get("contact_name", "").strip()
    booster = data.get("is_booster", False)

    if not company or not contact:
        return jsonify({"error": "company and contact_name required"}), 400

    records = load_tracker()
    record  = mark_responded(records, company, contact, booster)
    if not record:
        return jsonify({"error": f"{contact} @ {company} not found"}), 404

    save_tracker(records)
    return jsonify({"ok": True, "status": record.status})


# ── LAMP API ──────────────────────────────────────────────────────────────────

@app.route("/api/lamp")
def api_lamp():
    lamp = _load("lamp_list.json")
    if isinstance(lamp, dict):
        lamp = list(lamp.values())
    lamp.sort(key=lambda e: (-e.get("motivation", 5), -e.get("lamp_score", 0)))
    return jsonify({"entries": lamp, "total": len(lamp)})


@app.route("/api/lamp/motivation", methods=["POST"])
def api_lamp_motivation():
    from skills.lamp_list import load_lamp_list, save_lamp_list
    from skills.shared import DATA_DIR as SD
    data   = request.get_json()   # {"company": "Stripe", "motivation": 9}
    company = data.get("company", "").strip()
    motivation = int(data.get("motivation", 5))

    if not company:
        return jsonify({"error": "company required"}), 400
    if not 1 <= motivation <= 10:
        return jsonify({"error": "motivation must be 1-10"}), 400

    entries = load_lamp_list(SD / "lamp_list.json")
    found   = False
    for e in entries:
        if e.company.lower() == company.lower():
            e.motivation = motivation
            found = True
            break

    if not found:
        return jsonify({"error": f"{company} not found in LAMP list"}), 404

    save_lamp_list(entries, SD / "lamp_list.json")
    return jsonify({"ok": True})


# ── Events API ────────────────────────────────────────────────────────────────

@app.route("/api/events")
def api_events():
    events = _load("events_cache.json")
    today  = date.today()
    result = []
    for e in events:
        date_str = e.get("date", "")
        days_away = None
        if date_str and date_str.lower() not in ("tbd", "recurring", "various"):
            try:
                ev_date   = date.fromisoformat(date_str[:10])
                days_away = (ev_date - today).days
            except ValueError:
                pass
        result.append({**e, "days_away": days_away})
    result.sort(key=lambda x: (x["days_away"] is None, x.get("days_away", 9999)))
    return jsonify({"events": result, "total": len(result)})


# ── Leads API ─────────────────────────────────────────────────────────────────

@app.route("/api/leads")
def api_leads():
    leads = _load("leads_pipeline.json")
    leads.sort(key=lambda l: l.get("net_score", 0), reverse=True)
    return jsonify({"leads": leads, "total": len(leads)})


# ── Gmail Scan API ────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def api_scan():
    if _scan_status["running"]:
        return jsonify({"ok": False, "message": "Scan already in progress"})

    def _run():
        _scan_status["running"] = True
        try:
            from skills.gmail_monitor import run_monitor_cycle
            result = run_monitor_cycle()
            _scan_status["last_result"] = result
            _scan_status["last_run"]    = datetime.now().isoformat()
        except Exception as e:
            _scan_status["last_result"] = f"Error: {e}"
        finally:
            _scan_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "Scan started"})


@app.route("/api/scan/status")
def api_scan_status():
    return jsonify(_scan_status)


# ── LinkedIn API ─────────────────────────────────────────────────────────────

@app.route("/api/linkedin/auth/status")
def api_linkedin_auth_status():
    from skills.linkedin_engine import get_auth_status
    return jsonify(get_auth_status())


@app.route("/api/linkedin/auth/start", methods=["POST"])
def api_linkedin_auth_start():
    """Return auth URL for the frontend to open; auth runs in background thread."""
    import os, secrets
    from urllib.parse import urlencode
    from skills.linkedin_engine import (
        LINKEDIN_AUTH_URL, LINKEDIN_SCOPES, OAUTH_REDIRECT_URI,
        authenticate_linkedin,
    )
    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
    if not client_id:
        return jsonify({"error": "LINKEDIN_CLIENT_ID not set in .env"}), 400

    # Run the full auth flow (opens browser) in a background thread
    def _do_auth():
        try:
            authenticate_linkedin()
        except Exception as e:
            pass  # Errors visible in terminal

    threading.Thread(target=_do_auth, daemon=True).start()

    state = secrets.token_urlsafe(16)
    auth_url = f"{LINKEDIN_AUTH_URL}?{urlencode({'response_type':'code','client_id':client_id,'redirect_uri':OAUTH_REDIRECT_URI,'state':state,'scope':' '.join(LINKEDIN_SCOPES)})}"
    return jsonify({"ok": True, "auth_url": auth_url, "message": "Browser opened for LinkedIn auth. Return here after granting access."})


@app.route("/api/linkedin/drafts")
def api_linkedin_drafts():
    from skills.linkedin_engine import load_drafts
    drafts  = load_drafts()
    visible = [d for d in drafts if d.status in ("pending", "scheduled")]
    visible.sort(key=lambda d: d.created_at, reverse=True)
    return jsonify({
        "drafts": [vars(d) if not hasattr(d, '__dataclass_fields__') else __import__('dataclasses').asdict(d) for d in visible],
        "total":  len(visible),
        "published": sum(1 for d in drafts if d.status == "published"),
    })


@app.route("/api/linkedin/drafts/scan", methods=["POST"])
def api_linkedin_scan():
    if _li_scan_status["running"]:
        return jsonify({"ok": False, "message": "Scan already in progress"})

    def _run():
        _li_scan_status["running"] = True
        try:
            from skills.linkedin_engine import scrape_linkedin_feed, draft_comments_batch, import_content_drafts, load_drafts, save_drafts, _filter_relevant_posts
            import os
            apify_key = os.environ.get("APIFY_API_KEY", "")
            new_drafts = []
            if apify_key:
                posts = scrape_linkedin_feed(apify_key, max_posts=30)
                comment_drafts = draft_comments_batch(posts, n=10)
                new_drafts.extend(comment_drafts)
            post_drafts = import_content_drafts()
            new_drafts.extend(post_drafts)
            if new_drafts:
                existing = load_drafts()
                existing.extend(new_drafts)
                save_drafts(existing)
            _li_scan_status["last_result"] = f"Added {len(new_drafts)} drafts ({sum(1 for d in new_drafts if d.type=='comment')} comments, {sum(1 for d in new_drafts if d.type=='post')} posts)"
            _li_scan_status["last_run"] = datetime.now().isoformat()
        except Exception as e:
            _li_scan_status["last_result"] = f"Error: {e}"
        finally:
            _li_scan_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "LinkedIn scan started"})


@app.route("/api/linkedin/drafts/scan/status")
def api_linkedin_scan_status():
    return jsonify(_li_scan_status)


@app.route("/api/linkedin/drafts/add-url", methods=["POST"])
def api_linkedin_add_url():
    from skills.linkedin_engine import add_manual_comment_from_url
    import dataclasses
    data       = request.get_json()
    url        = data.get("url", "").strip()
    author     = data.get("author", "").strip()
    auth_title = data.get("author_title", "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400

    def _run():
        add_manual_comment_from_url(url, author=author, author_title=auth_title)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": f"Drafting comment for {url} (runs in background)"})


@app.route("/api/linkedin/drafts/add-post", methods=["POST"])
def api_linkedin_add_post():
    from skills.linkedin_engine import add_manual_post
    import dataclasses
    data = request.get_json()
    body = data.get("body", "").strip()
    url  = data.get("source_url", "").strip()
    if not body:
        return jsonify({"error": "body required"}), 400
    draft = add_manual_post(body, source_url=url)
    return jsonify({"ok": True, "draft": dataclasses.asdict(draft)})


@app.route("/api/linkedin/drafts/<draft_id>/approve", methods=["POST"])
def api_linkedin_approve(draft_id):
    from skills.linkedin_engine import load_drafts, save_drafts, next_optimal_slot
    drafts = load_drafts()
    draft  = next((d for d in drafts if d.draft_id == draft_id), None)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404
    # Set scheduled time (use existing if already set, else compute new optimal slot)
    if not draft.scheduled_time:
        draft.scheduled_time = next_optimal_slot().isoformat()
    draft.status = "scheduled"
    save_drafts(drafts)
    try:
        dt = datetime.fromisoformat(draft.scheduled_time)
        sched_label = dt.strftime("%a %b %-d · %-I:%M %p")
    except ValueError:
        sched_label = draft.scheduled_time
    return jsonify({"ok": True, "scheduled_time": draft.scheduled_time, "label": sched_label})


@app.route("/api/linkedin/drafts/<draft_id>/edit", methods=["POST"])
def api_linkedin_edit(draft_id):
    from skills.linkedin_engine import load_drafts, save_drafts
    import dataclasses
    data   = request.get_json()
    drafts = load_drafts()
    draft  = next((d for d in drafts if d.draft_id == draft_id), None)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404
    if "body" in data:
        draft.body         = data["body"]
    if "comment_body" in data:
        draft.comment_body = data["comment_body"]
    if "scheduled_time" in data:
        draft.scheduled_time = data["scheduled_time"]
    save_drafts(drafts)
    return jsonify({"ok": True, "draft": dataclasses.asdict(draft)})


@app.route("/api/linkedin/drafts/<draft_id>/discard", methods=["POST"])
def api_linkedin_discard(draft_id):
    from skills.linkedin_engine import load_drafts, save_drafts
    drafts = load_drafts()
    draft  = next((d for d in drafts if d.draft_id == draft_id), None)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404
    draft.status = "discarded"
    save_drafts(drafts)
    return jsonify({"ok": True})


# ── Entry point ───────────────────────────────────────────────────────────────

def run(port: int = 5050, open_browser: bool = True):
    if open_browser:
        import webbrowser, threading
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    print(f"\n  Job Search Dashboard → http://localhost:{port}\n  Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

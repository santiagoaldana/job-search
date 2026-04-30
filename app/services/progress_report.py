"""Progress report — compute job search health metrics from DB."""

from datetime import datetime, timedelta
from sqlmodel import Session, select
from app.models import Company, Contact, OutreachRecord, Lead


def compute_progress_report(session: Session) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    now = datetime.utcnow()
    week_ago = (now - timedelta(days=7)).isoformat()
    two_weeks_ago = (now - timedelta(days=14)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    # ── Pipeline velocity ─────────────────────────────────────────────────────
    companies = session.exec(
        select(Company).where(Company.is_archived == False)
    ).all()

    stage_order = ["pool", "researched", "outreach", "response", "meeting", "applied", "interview", "offer"]
    stage_counts = {s: 0 for s in stage_order}
    for c in companies:
        if c.stage in stage_counts:
            stage_counts[c.stage] += 1

    moved_this_week = sum(
        1 for c in companies
        if c.updated_at and c.updated_at >= week_ago and c.stage != "pool"
    )
    moved_prior_week = sum(
        1 for c in companies
        if c.updated_at and two_weeks_ago <= c.updated_at < week_ago and c.stage != "pool"
    )
    stalled = [
        c for c in companies
        if c.updated_at and c.updated_at < two_weeks_ago
        and c.stage in ("outreach", "response", "meeting")
    ]

    # ── Outreach funnel ───────────────────────────────────────────────────────
    all_outreach = session.exec(select(OutreachRecord)).all()

    sent_this_week = [r for r in all_outreach if r.sent_at and r.sent_at >= week_ago]
    sent_this_month = [r for r in all_outreach if r.sent_at and r.sent_at >= month_ago]
    total_sent = len(all_outreach)

    positive = [r for r in all_outreach if r.response_status == "positive"]
    ghosted = [r for r in all_outreach if r.response_status == "ghosted"]
    response_rate = round(len(positive) / total_sent * 100) if total_sent else 0

    # Avg days to positive reply (sent_at → updated_at proxy)
    reply_days = []
    for r in positive:
        if r.sent_at and r.updated_at:
            try:
                d = (datetime.fromisoformat(r.updated_at[:19]) - datetime.fromisoformat(r.sent_at[:19])).days
                if 0 <= d <= 60:
                    reply_days.append(d)
            except Exception:
                pass
    avg_reply_days = round(sum(reply_days) / len(reply_days)) if reply_days else None

    # Week-over-week outreach delta
    sent_prev_week = [r for r in all_outreach if r.sent_at and two_weeks_ago <= r.sent_at < week_ago]

    # ── Follow-up health ──────────────────────────────────────────────────────
    pending = [r for r in all_outreach if r.response_status == "pending"]
    overdue_day3 = [
        r for r in pending
        if r.follow_up_3_due and r.follow_up_3_due <= today and not r.follow_up_3_sent
    ]
    overdue_day7 = [
        r for r in pending
        if r.follow_up_7_due and r.follow_up_7_due <= today
        and r.follow_up_3_sent and not r.follow_up_7_sent
    ]
    needs_linkedin_dm = [
        r for r in pending
        if r.follow_up_7_sent and r.channel == "email"
    ]
    # Only count if contact is 1st-degree
    needs_linkedin_dm_count = 0
    for r in needs_linkedin_dm:
        if r.contact_id:
            contact = session.get(Contact, r.contact_id)
            if contact and contact.connection_degree == 1:
                needs_linkedin_dm_count += 1

    # ── Contact gaps ──────────────────────────────────────────────────────────
    company_ids_with_outreach = {r.company_id for r in all_outreach}
    company_ids_with_contacts = {
        c.company_id for c in session.exec(
            select(Contact).where(Contact.company_id != None)
        ).all()
    }
    high_motivation = [c for c in companies if c.motivation >= 7]
    no_contact = [c for c in high_motivation if c.id not in company_ids_with_contacts]
    contact_no_outreach = [
        c for c in high_motivation
        if c.id in company_ids_with_contacts and c.id not in company_ids_with_outreach
    ]

    return {
        "generated_at": now.isoformat(),
        "pipeline": {
            "stage_counts": stage_counts,
            "moved_this_week": moved_this_week,
            "moved_prior_week": moved_prior_week,
            "stalled": [{"id": c.id, "name": c.name, "stage": c.stage} for c in stalled[:5]],
            "stalled_count": len(stalled),
        },
        "outreach": {
            "total_sent": total_sent,
            "sent_this_week": len(sent_this_week),
            "sent_prior_week": len(sent_prev_week),
            "sent_this_month": len(sent_this_month),
            "positive_count": len(positive),
            "ghosted_count": len(ghosted),
            "response_rate_pct": response_rate,
            "avg_reply_days": avg_reply_days,
        },
        "followups": {
            "overdue_day3": len(overdue_day3),
            "overdue_day7": len(overdue_day7),
            "total_overdue": len(overdue_day3) + len(overdue_day7),
            "needs_linkedin_dm": needs_linkedin_dm_count,
        },
        "gaps": {
            "high_motivation_total": len(high_motivation),
            "no_contact_count": len(no_contact),
            "no_contact": [{"id": c.id, "name": c.name, "motivation": c.motivation} for c in no_contact[:5]],
            "contact_no_outreach_count": len(contact_no_outreach),
            "contact_no_outreach": [{"id": c.id, "name": c.name} for c in contact_no_outreach[:5]],
        },
    }


def render_progress_html(data: dict) -> str:
    """Render progress report as Claude-branded HTML artifact."""
    p = data["pipeline"]
    o = data["outreach"]
    f = data["followups"]
    g = data["gaps"]
    generated = data["generated_at"][:10]

    def trend(current, prior, higher_is_better=True):
        if prior == 0:
            return ""
        delta = current - prior
        if delta == 0:
            return '<span style="color:#6b7280">→ same</span>'
        up = delta > 0
        good = up if higher_is_better else not up
        color = "#16a34a" if good else "#dc2626"
        arrow = "↑" if up else "↓"
        return f'<span style="color:{color}">{arrow} {abs(delta)}</span>'

    funnel_stages = ["pool", "researched", "outreach", "response", "meeting", "applied", "interview"]
    funnel_html = ""
    for i, stage in enumerate(funnel_stages):
        count = p["stage_counts"].get(stage, 0)
        is_last = i == len(funnel_stages) - 1
        funnel_html += f'<span style="background:#fff;border:1px solid #e8e0d8;border-radius:8px;padding:4px 10px;font-size:13px"><strong>{count}</strong> <span style="color:#78716c">{stage}</span></span>'
        if not is_last:
            funnel_html += '<span style="color:#c96442;margin:0 4px">→</span>'

    stalled_html = ""
    for c in p["stalled"]:
        stalled_html += f'<div style="font-size:13px;color:#78716c;margin-top:4px">• {c["name"]} <span style="color:#c96442">({c["stage"]})</span></div>'

    no_contact_html = ""
    for c in g["no_contact"]:
        no_contact_html += f'<div style="font-size:13px;color:#78716c;margin-top:4px">• {c["name"]} <span style="color:#6b7280">(motivation {c["motivation"]})</span></div>'

    overdue_color = "#dc2626" if f["total_overdue"] > 0 else "#16a34a"
    rr_color = "#16a34a" if o["response_rate_pct"] >= 20 else "#dc2626" if o["response_rate_pct"] < 10 else "#6b7280"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Search Progress</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #f5f0eb; margin: 0; padding: 20px; color: #1c1917; }}
  h1 {{ font-size: 20px; font-weight: 700; margin: 0 0 2px 0; color: #1c1917; }}
  .subtitle {{ font-size: 13px; color: #78716c; margin-bottom: 20px; }}
  .card {{ background: #fff; border: 1px solid #e8e0d8; border-radius: 12px; padding: 16px; margin-bottom: 14px; }}
  .section-title {{ font-size: 12px; font-weight: 700; color: #c96442; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }}
  .metric-row {{ display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 10px; }}
  .metric {{ min-width: 80px; }}
  .metric-value {{ font-size: 28px; font-weight: 700; color: #1c1917; line-height: 1; }}
  .metric-label {{ font-size: 12px; color: #78716c; margin-top: 2px; }}
  .funnel {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 10px; }}
  .divider {{ border: none; border-top: 1px solid #f0ebe4; margin: 10px 0; }}
</style>
</head>
<body>
<h1>Job Search Health</h1>
<div class="subtitle">Generated {generated}</div>

<div class="card">
  <div class="section-title">Pipeline Velocity</div>
  <div class="funnel">{funnel_html}</div>
  <hr class="divider">
  <div class="metric-row">
    <div class="metric">
      <div class="metric-value">{p["moved_this_week"]}</div>
      <div class="metric-label">moved forward this week {trend(p["moved_this_week"], p["moved_prior_week"])}</div>
    </div>
    <div class="metric">
      <div class="metric-value" style="color:{'#dc2626' if p['stalled_count'] > 0 else '#16a34a'}">{p["stalled_count"]}</div>
      <div class="metric-label">stalled 14+ days</div>
    </div>
  </div>
  {stalled_html}
</div>

<div class="card">
  <div class="section-title">Outreach Funnel</div>
  <div class="metric-row">
    <div class="metric">
      <div class="metric-value">{o["sent_this_week"]}</div>
      <div class="metric-label">sent this week {trend(o["sent_this_week"], o["sent_prior_week"])}</div>
    </div>
    <div class="metric">
      <div class="metric-value">{o["sent_this_month"]}</div>
      <div class="metric-label">sent this month</div>
    </div>
    <div class="metric">
      <div class="metric-value" style="color:{rr_color}">{o["response_rate_pct"]}%</div>
      <div class="metric-label">response rate</div>
    </div>
    <div class="metric">
      <div class="metric-value" style="color:#6b7280">{o["ghosted_count"]}</div>
      <div class="metric-label">ghosted</div>
    </div>
  </div>
  {f'<div style="font-size:13px;color:#78716c">Avg reply: {o["avg_reply_days"]}d</div>' if o["avg_reply_days"] else ''}
</div>

<div class="card">
  <div class="section-title">Follow-up Health</div>
  <div class="metric-row">
    <div class="metric">
      <div class="metric-value" style="color:{overdue_color}">{f["total_overdue"]}</div>
      <div class="metric-label">overdue follow-ups</div>
    </div>
    <div class="metric">
      <div class="metric-value">{f["overdue_day3"]}</div>
      <div class="metric-label">Day 3 overdue</div>
    </div>
    <div class="metric">
      <div class="metric-value">{f["overdue_day7"]}</div>
      <div class="metric-label">Day 7 overdue</div>
    </div>
    <div class="metric">
      <div class="metric-value" style="color:#7c3aed">{f["needs_linkedin_dm"]}</div>
      <div class="metric-label">need LinkedIn DM</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="section-title">Contact Gaps</div>
  <div class="metric-row">
    <div class="metric">
      <div class="metric-value" style="color:{'#dc2626' if g['no_contact_count'] > 0 else '#16a34a'}">{g["no_contact_count"]}</div>
      <div class="metric-label">high-motivation, no contact</div>
    </div>
    <div class="metric">
      <div class="metric-value" style="color:#6b7280">{g["contact_no_outreach_count"]}</div>
      <div class="metric-label">contact found, not reached</div>
    </div>
  </div>
  {no_contact_html}
</div>

</body>
</html>"""

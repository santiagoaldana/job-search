"""
SQLModel table definitions for Job Search System v2.
Dates stored as ISO strings (YYYY-MM-DD) for SQLModel 0.0.x / Python 3.9 compatibility.
"""

from datetime import datetime
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship


# ── Company (LAMP record) ─────────────────────────────────────────────────────

class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    # LAMP scores
    lamp_score: float = Field(default=5.0)
    motivation: int = Field(default=5)
    advocacy_score: float = Field(default=1.0)
    postings_score: float = Field(default=1.0)

    # Funnel stage: pool|researched|outreach|response|meeting|applied|interview|offer|closed
    stage: str = Field(default="pool")

    # Visibility
    is_archived: bool = Field(default=False)
    suggested_by_ai: bool = Field(default=False)

    # Company metadata
    funding_stage: str = Field(default="unknown")  # series_b|series_c|series_d|series_e|series_f|series_g|series_h|public|unknown
    headcount_range: str = Field(default="unknown")  # 1-50|51-200|201-500|500+|unknown

    # Scraper routing
    career_page_url: Optional[str] = Field(default=None)
    greenhouse_slug: Optional[str] = Field(default=None)
    lever_slug: Optional[str] = Field(default=None)
    ashby_slug: Optional[str] = Field(default=None)
    wttj_slug: Optional[str] = Field(default=None)  # Welcome to the Jungle

    # Enrichment
    crunchbase_url: Optional[str] = Field(default=None)
    apollo_enriched_at: Optional[str] = Field(default=None)  # ISO datetime, rate-limit guard

    # Intelligence
    intel_summary: Optional[str] = Field(default=None)
    recent_news: Optional[str] = Field(default=None)  # JSON string
    org_notes: Optional[str] = Field(default=None)
    last_intel_refresh: Optional[str] = Field(default=None)  # ISO datetime string
    network_path_json: Optional[str] = Field(default=None)  # JSON cache of last network path analysis

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # Relationships
    contacts: List["Contact"] = Relationship(back_populates="company")
    leads: List["Lead"] = Relationship(back_populates="company")
    outreach_records: List["OutreachRecord"] = Relationship(back_populates="company")
    applications: List["Application"] = Relationship(back_populates="company")


# ── Contact ───────────────────────────────────────────────────────────────────

class Contact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)
    name: str
    title: Optional[str] = Field(default=None)
    linkedin_url: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    connection_degree: int = Field(default=1)  # 1=direct, 2=2nd, 3=3rd
    warmth: str = Field(default="cold")  # cold|warm|hot
    is_hiring_manager: bool = Field(default=False)
    outreach_status: str = Field(default="none")  # none|drafted|emailed|linkedin_dm|connection_requested|met
    connected_on: Optional[str] = Field(default=None)  # ISO date string
    met_via: Optional[str] = Field(default=None)
    relationship_notes: Optional[str] = Field(default=None)
    met_at_event_id: Optional[int] = Field(default=None)
    introduced_by_contact_id: Optional[int] = Field(default=None, foreign_key="contact.id")
    referral_target_company_id: Optional[int] = Field(default=None)
    email_guessed: bool = Field(default=False)              # pattern-guessed, not confirmed
    email_invalid: bool = Field(default=False)              # bounce confirmed
    email_patterns_tried: Optional[str] = Field(default=None)  # JSON list of tried patterns
    connection_request_variant: Optional[str] = Field(default=None)  # "A" or "B"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    company: Optional[Company] = Relationship(back_populates="contacts")
    outreach_records: List["OutreachRecord"] = Relationship(back_populates="contact")


# ── Lead (Job Opportunity) ────────────────────────────────────────────────────

class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)
    title: str
    url: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)

    # Fit scoring (0-100); null = not yet scored
    fit_score: Optional[float] = Field(default=None)
    fit_strengths: Optional[str] = Field(default=None)  # JSON list
    fit_gaps: Optional[str] = Field(default=None)        # JSON list
    # Cambridge/Boston/Remote=True; onsite-only elsewhere=False
    location_compatible: bool = Field(default=True)

    # Status: active|applied|closed|skipped
    status: str = Field(default="active")
    discard_reason: Optional[str] = Field(default=None)  # wrong_seniority|wrong_location|not_my_sector|no_real_posting
    # Source: greenhouse|lever|career_page
    source: str = Field(default="career_page")

    posted_date: Optional[str] = Field(default=None)   # ISO date string
    fetched_date: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    salary_min: Optional[int] = Field(default=None)
    salary_max: Optional[int] = Field(default=None)
    salary_currency: Optional[str] = Field(default="USD")
    salary_notes: Optional[str] = Field(default=None)

    company: Optional[Company] = Relationship(back_populates="leads")
    applications: List["Application"] = Relationship(back_populates="lead")


# ── OutreachRecord ────────────────────────────────────────────────────────────

class OutreachRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)
    contact_id: Optional[int] = Field(default=None, foreign_key="contact.id")
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")

    channel: str = Field(default="email")  # email|linkedin|referral
    sent_at: Optional[str] = Field(default=None)    # ISO datetime string
    subject: Optional[str] = Field(default=None)
    body: Optional[str] = Field(default=None)

    # pending|positive|negative|ghosted
    response_status: str = Field(default="pending")

    follow_up_3_due: Optional[str] = Field(default=None)   # ISO date string (3B7 day 3)
    follow_up_7_due: Optional[str] = Field(default=None)   # ISO date string (3B7 day 7)
    follow_up_3_sent: bool = Field(default=False)           # day-3 bump sent
    follow_up_7_sent: bool = Field(default=False)           # day-7 close sent
    linkedin_accepted: Optional[bool] = Field(default=None) # None=pending, True=accepted, False=not accepted
    notes: Optional[str] = Field(default=None)

    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    company: Optional[Company] = Relationship(back_populates="outreach_records")
    contact: Optional[Contact] = Relationship(back_populates="outreach_records")
    messages: List["ConversationMessage"] = Relationship(back_populates="outreach_record")


# ── ConversationMessage (Email thread history) ────────────────────────────────

class ConversationMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    outreach_record_id: int = Field(foreign_key="outreachrecord.id", index=True)
    message_date: str  # ISO datetime string
    from_email: str
    from_name: Optional[str] = Field(default=None)
    to_email: str
    subject: Optional[str] = Field(default=None)
    body_full: str  # Complete email body (not truncated)
    message_type: str  # "outreach" | "reply" | "follow_up"
    gmail_message_id: Optional[str] = Field(default=None)  # For Gmail dedup
    outlook_message_id: Optional[str] = Field(default=None)  # For Outlook dedup
    thread_id: Optional[str] = Field(default=None)  # Gmail threadId
    conversation_id: Optional[str] = Field(default=None)  # Outlook conversationId
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    outreach_record: Optional[OutreachRecord] = Relationship(back_populates="messages")


# ── Application ───────────────────────────────────────────────────────────────

class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id", index=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")

    applied_date: Optional[str] = Field(default=None)    # ISO date string
    cv_version_path: Optional[str] = Field(default=None) # cv/versions/<slug>.json
    cover_notes: Optional[str] = Field(default=None)

    # draft|pending_review|approved|submitted|screen|interview|offer|rejected|withdrawn
    status: str = Field(default="draft")

    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    company: Optional[Company] = Relationship(back_populates="applications")
    lead: Optional[Lead] = Relationship(back_populates="applications")
    interviews: List["Interview"] = Relationship(back_populates="application")
    offers: List["Offer"] = Relationship(back_populates="application")


# ── Interview ─────────────────────────────────────────────────────────────────

class Interview(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    scheduled_at: Optional[str] = Field(default=None)   # ISO datetime string
    type: str = Field(default="video")                  # phone|video|onsite
    interviewer_name: Optional[str] = Field(default=None)
    prep_notes: Optional[str] = Field(default=None)
    outcome: Optional[str] = Field(default=None)         # advancing|rejected|pending
    feedback: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    application: Optional[Application] = Relationship(back_populates="interviews")


# ── Offer ─────────────────────────────────────────────────────────────────────

class Offer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: Optional[int] = Field(default=None, foreign_key="application.id", index=True)
    received_date: Optional[str] = Field(default=None)  # ISO date string
    title: Optional[str] = Field(default=None)
    salary: Optional[str] = Field(default=None)
    equity: Optional[str] = Field(default=None)
    start_date: Optional[str] = Field(default=None)     # ISO date string
    notes: Optional[str] = Field(default=None)
    decision: Optional[str] = Field(default=None)       # accepted|declined|negotiating|pending
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    application: Optional[Application] = Relationship(back_populates="offers")


# ── Event ─────────────────────────────────────────────────────────────────────

class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    date: Optional[str] = Field(default=None)           # ISO date string
    location: Optional[str] = Field(default=None)
    url: Optional[str] = Field(default=None)
    cost: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    category: str = Field(default="strategic")           # high_probability|strategic|wildcard
    utility: float = Field(default=5.0)
    risk: float = Field(default=5.0)
    net_score: float = Field(default=3.0)
    action_prompt: Optional[str] = Field(default=None)
    meetings_booked: int = Field(default=0)
    is_registered: bool = Field(default=False)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── ContentDraft (LinkedIn posts) ─────────────────────────────────────────────

class ContentDraft(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_url: Optional[str] = Field(default=None)
    source_title: Optional[str] = Field(default=None)
    body: str
    net_score: float = Field(default=0.0)
    controversy_score: float = Field(default=0.0)
    risk_score: float = Field(default=0.0)
    # pending|approved|scheduled|published|discarded
    status: str = Field(default="pending")
    scheduled_at: Optional[str] = Field(default=None)   # ISO datetime string
    published_at: Optional[str] = Field(default=None)   # ISO datetime string
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    content_type: Optional[str] = Field(default="linkedin")  # linkedin|substack


# ── ContentFeed (thought leader / publication RSS feeds) ──────────────────────

class ContentFeed(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    url: str = Field(index=True)
    category: str = Field(default="publication")  # thought_leader | publication | news
    active: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── AITargetSuggestion (weekly startup discovery) ─────────────────────────────

class Reference(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    contact_id: Optional[int] = Field(default=None, foreign_key="contact.id")
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")
    contact_name: str
    contact_title: Optional[str] = Field(default=None)
    relationship: Optional[str] = Field(default=None)  # "worked together at Uff Móvil"
    strength: str = Field(default="medium")             # strong|medium|weak
    role_types: Optional[str] = Field(default=None)     # comma-separated: "payments,fintech"
    notes: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class DismissedBriefAction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    action_type: str = Field(index=True)
    payload_id: Optional[int] = Field(default=None, index=True)
    dismissed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AITargetSuggestion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    reason: str                          # why Claude suggested this company
    funding_stage: Optional[str] = Field(default=None)
    location_notes: Optional[str] = Field(default=None)
    domain: Optional[str] = Field(default=None)  # payments|identity|agentic_ai|embedded_banking
    suggested_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    reviewed: bool = Field(default=False)
    approved: bool = Field(default=False)
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")


# ── GmailSyncState ────────────────────────────────────────────────────────────

class GmailSyncState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_email: str = Field(index=True, unique=True)
    last_poll_at: Optional[str] = Field(default=None)       # ISO datetime of last sync
    last_sync_summary: Optional[str] = Field(default=None)  # JSON: {new_outreach, new_replies, linkedin_accepted}
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── StrategyConfig (single-row priority settings) ─────────────────────────────

class StrategyConfig(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    priority_company_ids: str = Field(default="[]")  # JSON list of company IDs
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

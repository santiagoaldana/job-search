"""
Content Intelligence Module — Job Search Orchestration System
Santiago Aldana | Executive Job Search

Monitors emerging trends in Fintech, Payments, Embedded Banking, BaaS,
Stablecoins, and Agentic Commerce via RSS feeds. Generates high-signal
LinkedIn post drafts that challenge industry status quos rather than follow them.

Scoring:
  Controversy Potential (1-10): Likelihood to generate substantive debate
  Credibility Risk (1-10): Likelihood to backfire or appear uninformed
  Net Score = Controversy - (Credibility_Risk * 0.4)

Usage:
  python3 -m skills.content_intelligence
  python3 -m skills.content_intelligence --days 14 --drafts 3 --no-enrich
"""

import json
import re
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
import feedparser
import anthropic

from skills.shared import (
    EXECUTIVE_PROFILE, MODEL_OPUS, MODEL_HAIKU, DATA_DIR, compute_net_score
)

# ── RSS Feed Sources ──────────────────────────────────────────────────────────

RSS_FEEDS = {
    "TechCrunch Fintech": "https://techcrunch.com/category/fintech/feed/",
    "PYMNTS":             "https://www.pymnts.com/feed/",
    "Finextra":           "https://www.finextra.com/rss/headlines.aspx",
    "a16z":               "https://a16z.com/feed/",
    "The Financial Brand": "https://thefinancialbrand.com/feed/",
    "Payments Dive":      "https://www.paymentsdive.com/feeds/news/",
    "Banking Dive":       "https://www.bankingdive.com/feeds/news/",
}

TOPIC_FOCUS = [
    "stablecoin", "stablecoins", "embedded banking", "embedded finance",
    "BaaS", "banking as a service", "agentic AI", "agentic commerce",
    "payments infrastructure", "open banking", "digital identity",
    "BNPL", "cross-border payments", "tokenization", "real-time payments",
    "RTP", "FedNow", "central bank digital currency", "CBDC",
    "fraud prevention", "KYC", "AML", "crypto payments", "fintech",
    "neobank", "challenger bank", "payment orchestration", 
]

# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class Article:
    title: str
    url: str
    source: str
    published: str      # ISO date string
    summary: str        # Feed-provided excerpt (may be empty)
    relevance_score: float = 0.0   # 0.0–1.0 from Haiku classification


@dataclass
class LinkedInDraft:
    article_title: str
    article_url: str
    source: str
    draft_text: str
    controversy_potential: int   # 1-10
    credibility_risk: int        # 1-10
    net_score: float
    positioning_angle: str       # one-line description of the contrarian take


# ── RSS Fetching ──────────────────────────────────────────────────────────────

def _parse_date(entry) -> str:
    """Extract published date from feedparser entry. Returns ISO string or empty."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                pass
    return ""


def fetch_rss_feeds(feeds: dict = RSS_FEEDS, max_age_days: int = 7) -> list[Article]:
    """
    Fetch all configured RSS feeds. Filter to articles published within max_age_days.
    Returns deduped list of Article objects sorted by published date descending.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_age_days)
    articles: list[Article] = []
    seen_urls: set[str] = set()

    for source_name, feed_url in feeds.items():
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                url = getattr(entry, "link", "") or ""
                if not url or url in seen_urls:
                    continue

                date_str = _parse_date(entry)
                # Filter by age if date available
                if date_str:
                    try:
                        pub_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if pub_dt < cutoff:
                            continue
                    except ValueError:
                        pass  # Keep articles with unparseable dates

                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", "") or ""
                # Strip HTML tags from summary
                summary = re.sub(r'<[^>]+>', '', summary).strip()[:500]

                if not title:
                    continue

                seen_urls.add(url)
                articles.append(Article(
                    title=title,
                    url=url,
                    source=source_name,
                    published=date_str,
                    summary=summary,
                ))
                count += 1

            print(f"[Content Intelligence] {source_name}: {count} articles fetched")
        except Exception as e:
            print(f"[Content Intelligence] Error fetching {source_name}: {e}")

    articles.sort(key=lambda a: a.published, reverse=True)
    print(f"[Content Intelligence] Total articles: {len(articles)}")
    return articles


# ── Relevance Classification ──────────────────────────────────────────────────

def classify_relevance(articles: list[Article], batch_size: int = 10) -> list[Article]:
    """
    Use Claude Haiku in batches to score each article for relevance (0.0–1.0)
    to Santiago's domain. Articles with score < 0.6 are filtered out.

    Batch strategy: 10 articles per API call to minimize token cost.
    Returns articles sorted by relevance_score descending.
    """
    if not articles:
        return []

    client = anthropic.Anthropic()
    scored: list[Article] = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        items_text = "\n".join(
            f'{j+1}. TITLE: {a.title}\n   SUMMARY: {a.summary[:200] or "(no summary)"}'
            for j, a in enumerate(batch)
        )
        prompt = f"""Score each article for relevance to this executive's domain.

Executive domain: FinTech, payments infrastructure, embedded banking, BaaS, stablecoins,
Agentic AI in financial services, digital identity, fraud prevention, open banking, LATAM markets.

Articles to score:
{items_text}

Return ONLY a valid JSON array of {len(batch)} numbers between 0.0 and 1.0.
Example: [0.9, 0.3, 0.7, 0.1, 0.8, 0.4, 0.6, 0.2, 0.95, 0.5]
No explanation. Just the array."""

        try:
            response = client.messages.create(
                model=MODEL_HAIKU,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            scores = json.loads(raw)
            if len(scores) != len(batch):
                scores = [0.5] * len(batch)  # Fallback
        except Exception as e:
            print(f"[Content Intelligence] Haiku classification error: {e}")
            scores = [0.5] * len(batch)

        for article, score in zip(batch, scores):
            article.relevance_score = float(score)
            if float(score) >= 0.6:
                scored.append(article)

    scored.sort(key=lambda a: a.relevance_score, reverse=True)
    print(f"[Content Intelligence] {len(scored)} articles passed relevance threshold (≥0.6)")
    return scored


# ── LinkedIn Post Drafting ────────────────────────────────────────────────────

# Agentic commerce arc angles drawn from Santiago's SupplyMind build.
# SupplyMind is a live prototype of a multi-agent B2B commerce system using
# MCP (Anthropic), A2A (Google DeepMind), UCP, and an Agentic Payment Interface.
# Santiago is building this at SMCU as applied R&D — it is not a tutorial follow-along.
#
# SMCU / Credit Union framing is intentional: Santiago uses his current CPSO role as a
# launchpad and credibility signal, not as a destination. Mentioning SMCU and the
# credit union context ("finding startup partners," "scouting the NANDA ecosystem for SMBs")
# is a legitimate transition tactic: it positions him as a high-status buyer/partner,
# not a job candidate. Do NOT strip this framing out.
#
# Arc structure: each angle below can stand alone or chain into a 2-3 post series.
# For series posts, use the Loop & Hook technique: reference the previous post's open
# question (Loop) and end with a new tension or teaser (Hook).
SUPPLYMIND_CONTENT_ARCS = """
AGENTIC COMMERCE CONTENT ARCS (draw from these when the news article touches AI agents,
BaaS, embedded finance, payments infrastructure, or agentic commerce):

Arc 1 — The Trust Gap (standalone or Day 1 of a series)
Core tension: If an agent is doing the buying, who underwrites the trust? A credit card is
a human instrument. Programmable spending mandates (AP2) are agent instruments. Most
BaaS platforms are not built for the latter.
Quotable seed: "Traditional BaaS embeds a button. Agentic BaaS embeds a bank account
and a decision engine directly into the agent."
Hook for series: "If your business had an autonomous agent today, would you trust it with
your credit line?" (The answer should be no, and that gap is the business opportunity.)

Arc 2 — The Machine Handshake (standalone or Day 2)
Core tension: The payments industry is focused on the LLM layer. The real infrastructure
gap is one layer below: agent discovery (A2A / NANDA), always-on execution (Maritime /
agentic cloud), and machine-native settlement (x402, MPP, USDC nanopayments). Santiago
is building all three in SupplyMind and finding the friction points firsthand.
Quotable seed: "Building this revealed that agents fail at the handshake, not the reasoning.
The LLM is fine. The schema contract underneath it is where things break."
Loop from Arc 1: "Yesterday I asked about trust. Here is the infrastructure that makes
trust programmable."

Arc 3 — ABaaS: The New Category (standalone or Day 3)
Core tension: Agentic Banking-as-a-Service (ABaaS) is not an incremental improvement on
BaaS. It requires three new primitives that legacy BaaS platforms do not provide: Verified
Agent Identity (KYA, not KYC), Programmable Spending Mandates (AP2, not static limits),
and machine-native settlement rails (not T+2 ACH). The companies that build these
primitives will define the next decade of embedded finance.
Quotable seed: "We are moving toward a world where checkout is an API handshake, not
a user interface. The question is who owns the trust layer."
SMCU framing: Santiago is scouting for startup partners building in NANDA, Maritime, and
x402 ecosystems to bring Agentic BaaS to credit union SMBs. This is a legitimate buyer
signal, not a job search signal.

Arc 4 — The Execution Gap in Agentic AI (standalone, high controversy)
Core tension: Every major payments company is announcing "agentic AI" features. Almost
none of them have solved the identity problem for agents (KYA), the authorization problem
(who sets the mandate and under what compliance framework), or the settlement problem
(how do you do real-time finality without stablecoin rails). Santiago has built enough of
SupplyMind to know exactly where the enterprise implementations will break.
Quotable seed: "The Execution Gap in agentic AI is not the model. It is the compliance
wrapper around the agent's financial authority."

Arc 5 — Vibe Coding as Executive Methodology (standalone, personal/differentiated)
Core tension: "Vibe coding" is dismissed as a junior developer shortcut. Santiago uses it
as a strategic prototyping method: build a working system fast enough to find the real
friction points before writing a business case. SupplyMind was built this way. The insight
is that hands-on prototyping at the executive level is the fastest path to identifying where
the market is wrong about what the hard problem actually is.
Quotable seed: "I built SupplyMind to find out where agentic commerce breaks. You cannot
find those failure points from a whitepaper."

HASHTAG GUIDANCE: Use whatever number of hashtags serves the post (typically 3 to 6).
Rotate through: #AgenticAI #EmbeddedFinance #BaaS #AgenticCommerce #Payments
#FintechStrategy #EmbeddedBanking #DigitalIdentity #MCP #OpenBanking #CreditUnions
#SMB. Never exceed 8. Never use #Hiring or #OpenToWork.
"""

DRAFT_PROMPT = """You are a Strategic Executive Architect. You combine the high-stakes positioning of a PR Expert, the market-matching insight of an Executive Search Consultant, and the tactical communication style of a Leadership Coach. Your goal is to help Santiago build "Intellectual Authority" on LinkedIn without ever appearing to be job hunting.

EXECUTIVE PROFILE:
{profile}

AGENTIC COMMERCE CONTENT ARCS (use these as inspiration when relevant):
{arcs}

ARTICLE TO RESPOND TO:
Title: {title}
Source: {source}
URL: {url}
Summary: {summary}

WRITING PRINCIPLES:
- First Principles: Do not use clichés. Break every topic down to its fundamental truths (e.g., instead of "improving payments," discuss the "atomic unit of trust in digital exchange").
- Anti-Sales Mandate: Never use hashtags like #Hiring or #OpenToWork. Make Santiago appear so deeply embedded in the future of the industry that his "next move" feels like an inevitable evolution, not a request. Note: references to SMCU, credit unions, and scouting for startup partners are intentional transition tactics, not job-search signals; keep them when relevant.
- Style: Clever, minimalist, authoritative. Short, punchy sentences. No corporate jargon (use "friction" not "synergistic challenges"). No dashes: use colons, semicolons, and commas instead. No emojis.
- Hook: The first line must be a "Pattern Interrupt": it challenges a common assumption, states a surprising fact, or shows deep literacy on the topic.
- Avoid: "excited to share", "great article", "I believe", "thrilled", "honored", platitudes.

ANALYSIS FRAMEWORK (apply all three lenses in the post):
1. Macro Trend: Why does this topic matter to the economy or industry right now?
2. The "So What?": What is the non-obvious insight only Santiago can offer, grounded in specific career experience? (e.g., "When we scaled SoyYo to 3M users...", "At Avianca, managing $110M in IT spend taught me...", "Building SupplyMind taught me that agents fail at the handshake, not the reasoning...")
3. Call to Conversation: End with a high-level question that invites peers (CEOs, Founders) to comment: not rhetorical, but one where reasonable experts would genuinely disagree.

TRANSFORMATION FILTER: When the topic touches AI, Payments, Identity, or Stablecoins, position Santiago as the strategist who understands both the code and the culture, with the capacity to be hands-on as an entrepreneur and a senior executive in regulated industries. Highlight the Execution Gap: the distance between what the technology promises and what organizations can actually deliver.

TARGET AUDIENCE LENS: The primary readers Santiago wants to reach are operators and founders at growth-stage fintechs — specifically companies in BaaS, embedded finance, fraud/identity, and cross-border payments (e.g., Stripe, Brex, Synctera, Sardine, Flywire, Alloy, Airwallex). Write for the practitioner actively building, not the academic observer. The post should feel like it belongs in a product review or board meeting debate, not a newsletter digest.

SOURCE DIVERSITY MANDATE: Santiago's authority comes from having built and exited companies, and from hands-on prototyping (SupplyMind), not from citing publications. Extract the business signal from the article and reframe it through his operator lens. The article is a prompt, not a citation.

Generate a post of appropriate length to gain traction on LinkedIn (typically 150-300 words; longer if the topic demands depth).

Return ONLY valid JSON (no markdown, no explanation):
{{
  "draft": "<full LinkedIn post text>",
  "controversy_potential": <1-10 integer>,
  "credibility_risk": <1-10 integer>,
  "positioning_angle": "<one sentence: what contrarian angle does this take?>"
}}"""


def draft_linkedin_posts(articles: list[Article], n: int = 5) -> list[LinkedInDraft]:
    """
    Take top n articles by relevance and generate a LinkedIn post draft for each.
    Uses Claude Opus for generation quality.
    Returns list sorted by net_score descending.
    """
    client = anthropic.Anthropic()
    drafts: list[LinkedInDraft] = []

    for i, article in enumerate(articles[:n]):
        print(f"[Content Intelligence] Drafting post {i+1}/{min(n, len(articles))}: {article.title[:60]}...")

        prompt = DRAFT_PROMPT.format(
            profile=EXECUTIVE_PROFILE,
            arcs=SUPPLYMIND_CONTENT_ARCS,
            title=article.title,
            source=article.source,
            url=article.url,
            summary=article.summary[:400] or "(no summary available)",
        )

        try:
            response = client.messages.create(
                model=MODEL_OPUS,
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            result = json.loads(raw)

            controversy = int(result.get("controversy_potential", 5))
            cred_risk = int(result.get("credibility_risk", 5))
            net = compute_net_score(controversy, cred_risk)

            drafts.append(LinkedInDraft(
                article_title=article.title,
                article_url=article.url,
                source=article.source,
                draft_text=result.get("draft", ""),
                controversy_potential=controversy,
                credibility_risk=cred_risk,
                net_score=net,
                positioning_angle=result.get("positioning_angle", ""),
            ))
        except Exception as e:
            print(f"[Content Intelligence] Draft error for '{article.title[:40]}': {e}")

    drafts.sort(key=lambda d: d.net_score, reverse=True)
    return drafts


# ── Report Formatter ──────────────────────────────────────────────────────────

def format_report(drafts: list[LinkedInDraft], articles_count: int = 0) -> str:
    lines = [
        "# LinkedIn Content Drafts",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        f"_Articles scanned: {articles_count} | Drafts generated: {len(drafts)}_",
        f"_Scoring: Net = Controversy − (Credibility Risk × 0.4)_",
        "",
    ]

    for i, draft in enumerate(drafts, 1):
        lines += [
            f"## Draft {i} — {draft.positioning_angle}",
            f"**Source**: [{draft.article_title}]({draft.article_url}) via {draft.source}",
            f"**Scores**: Controversy: {draft.controversy_potential}/10 | "
            f"Credibility Risk: {draft.credibility_risk}/10 | **Net: {draft.net_score}**",
            "",
            "---",
            "",
            draft.draft_text,
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run(max_age_days: int = 7, n_drafts: int = 5, enrich: bool = True) -> str:
    """
    Main entry point for Module 1.

    Args:
        max_age_days: Only consider articles published in the last N days
        n_drafts: Number of LinkedIn drafts to generate
        enrich: Whether to call Claude (False = return articles list only, no drafts)

    Returns:
        Markdown report string. Also saves to data/content_drafts.md.
    """
    # 1. Fetch RSS
    articles = fetch_rss_feeds(max_age_days=max_age_days)
    if not articles:
        return "No articles found. Check RSS feed availability."

    drafts: list[LinkedInDraft] = []

    if enrich:
        # 2. Classify relevance
        relevant = classify_relevance(articles)
        if not relevant:
            return "No relevant articles found after classification."

        # 3. Draft posts
        drafts = draft_linkedin_posts(relevant, n=n_drafts)

    # 4. Format report
    report = format_report(drafts, articles_count=len(articles))

    # 5. Save
    output_path = DATA_DIR / "content_drafts.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"[Content Intelligence] Report saved to {output_path}")

    # Also cache raw drafts as JSON
    cache_path = DATA_DIR / "content_cache.json"
    cache_path.write_text(
        json.dumps([asdict(d) for d in drafts], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from pathlib import Path as _Path
    from dotenv import load_dotenv
    load_dotenv(_Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(description="Content Intelligence — generate LinkedIn drafts from FinTech news")
    parser.add_argument("--days", type=int, default=7, help="Max article age in days (default: 7)")
    parser.add_argument("--drafts", type=int, default=5, help="Number of LinkedIn drafts to generate (default: 5)")
    parser.add_argument("--no-enrich", action="store_true", help="Skip Claude drafting (article list only)")
    args = parser.parse_args()

    report = run(max_age_days=args.days, n_drafts=args.drafts, enrich=not args.no_enrich)
    print("\n" + "="*60)
    print(report)

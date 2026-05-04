"""
Shared constants and utilities for the Job Search Orchestration System.
All modules import from here to avoid drift.
"""

from pathlib import Path

# ── Directory Paths ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CV_OUTPUT_DIR = BASE_DIR / "cv" / "output"
CONTACTS_CSV = BASE_DIR / "cv" / "contacts_export.csv"
MASTER_CV_PATH = BASE_DIR / "Santiago Aldana 2025-12-09.pdf"

# Ensure output dirs exist at import time
DATA_DIR.mkdir(parents=True, exist_ok=True)
CV_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Executive Profile ─────────────────────────────────────────────────────────

EXECUTIVE_PROFILE = """
Santiago Aldana — MIT Sloan MBA, 20+ years in FinTech/AI/payments/LATAM.

Key credentials:
- CEO SoyYo (2020–2024): Digital identity & fraud prevention platform (bank JV),
  scaled to 3M+ users, sold to Redeban (Colombia's leading PSP)
- CDTO Avianca (2017–2019): $110M IT budget, $700–800M annual digital revenue,
  47% of sales migrated to digital
- CEO & Founder Uff Móvil (2010–2015): LatAm's first MVNO, 400K customers,
  sold to Bancolombia at $18M
- CIO Telefónica (2004–2009): €60M IT transformation across 5 countries in 17 months
- CEO IQ Outsourcing (2015–2017): Transformed BPO into digital solutions provider

Board roles:
- Tuya Credit Card (Open Banking strategy)
- Colombia Fintech (regulatory advocacy)
- Zulu (cross-border crypto payments)

Current:
- Chief Product & Solutions Officer, St. Mary's Credit Union (SMCU): Building
  fintech partnerships and CUSOs (Credit Union Service Organizations) to launch
  new financial services. Leveraging AI, payments, and blockchain expertise for
  agentic AI, fraud prevention, AI for financial processes, and marketing.
- Managing Partner, AI Data Solutions — exclusive LATAM distribution of
  Maven AGI (Agentic AI for CX).

Education: MIT Sloan MBA (Strategy, Innovation & Technology);
Industrial Engineering — Universidad de los Andes.
MIT Sloan Innovator Member. Attending MIT Sloan CIO Symposium 2026.

Target roles: C-suite or SVP in payments, embedded banking, Agentic AI,
or digital identity. Based in Boston, MA. Open to New York and remote-first.
Fully bilingual (English/Spanish). U.S. and Colombia work authorization.
""".strip()

# ── Scoring ───────────────────────────────────────────────────────────────────

def compute_net_score(utility: int, risk: int) -> float:
    """
    Universal net score formula used across all modules.
    Net Score = Utility - (Risk * 0.4)
    Utility and Risk are both 1-10 integer scales.
    """
    return round(utility - (risk * 0.4), 2)

# ── Claude Models ─────────────────────────────────────────────────────────────

MODEL_OPUS = "claude-opus-4-6"        # Generation: CV synthesis, post drafts, outreach scripts
MODEL_HAIKU = "claude-haiku-4-5-20251001"  # Classification: relevance scoring, lead scoring

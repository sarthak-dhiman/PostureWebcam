"""
constants.py — Design tokens, API endpoints, and timing constants.
"""

APP_NAME = "Posture Webcam Analyzer"
APP_VERSION = "1.0.0"

# ── API endpoints (local mock server) ───────────────────────────────────────
# During development the API points to a local mock running on port 8000.
API_BASE = "http://127.0.0.1:8000/v1"
API_LOGIN = f"{API_BASE}/auth/login"
API_GOOGLE_OAUTH = f"{API_BASE}/auth/google"
API_GOOGLE_POLL = f"{API_BASE}/auth/google/poll"
API_VERIFY = f"{API_BASE}/auth/verify"
API_JOIN_ORG = f"{API_BASE}/org/join"
API_CREATE_ORG = f"{API_BASE}/org/create"

BILLING_URL = "https://app.yourdomain.com/settings/billing"

# ── Timing ───────────────────────────────────────────────────────────────────
SUBSCRIPTION_CHECK_INTERVAL_MS = 12 * 60 * 60 * 1000  # 12 hours
LOGIN_MOCK_DELAY_S = 1.5

# ── Colour palette ──────────────────────────────────────────────────────────
class C:
    """Colour tokens used in both QSS and programmatic painting."""
    BG_PRIMARY      = "#0F1117"
    BG_SECONDARY    = "#1A1D27"
    BG_SIDEBAR      = "#141620"
    BG_INPUT        = "#232636"
    BG_HOVER        = "#2A2E3F"

    BORDER_SUBTLE   = "#2E3348"
    BORDER_FOCUS    = "#4F8CFF"

    TEXT_PRIMARY    = "#E8ECF4"
    TEXT_SECONDARY  = "#8B92A8"
    TEXT_DISABLED   = "#4A5068"

    ACCENT_BLUE     = "#4F8CFF"
    ACCENT_BLUE_HV  = "#6DA1FF"
    ACCENT_EMERALD  = "#34D399"
    ACCENT_AMBER    = "#FBBF24"
    ACCENT_RED      = "#F87171"

    WHITE           = "#FFFFFF"
    TRANSPARENT     = "transparent"

# ── Sidebar geometry ─────────────────────────────────────────────────────────
SIDEBAR_WIDTH = 220

# ── Page indices (inside QStackedWidget) ─────────────────────────────────────
PAGE_LOGIN      = 0
PAGE_JOIN_ORG   = 1
PAGE_DASHBOARD  = 2
PAGE_REPORTS    = 3
PAGE_ACCOUNT    = 4

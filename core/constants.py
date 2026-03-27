"""
constants.py — Design tokens, API endpoints, and timing constants.
"""

import json
import os
import sys
from pathlib import Path

APP_NAME = "Posture Webcam Analyzer"
APP_VERSION = "1.0.0"

# ── Runtime config (env + optional file) ────────────────────────────────────
def _bool_from_any(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ("1", "true", "yes", "on", "y")


def _runtime_base_dir() -> Path:
    # In PyInstaller --onedir builds, sys.executable points to dist/PostureApp/.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _load_runtime_config() -> dict:
    cfg_path = _runtime_base_dir() / "data" / "runtime_config.json"
    try:
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


_RUNTIME_CONFIG = _load_runtime_config()

# ── API endpoints (local mock server) ───────────────────────────────────────
# During development the API points to a local mock running on port 8000.
API_BASE = (
    os.getenv("POSTURE_API_BASE")
    or _RUNTIME_CONFIG.get("api_base")
    or "http://localhost:8000/api/v1"
)
API_LOGIN = f"{API_BASE}/auth/login"
API_GOOGLE_OAUTH = f"{API_BASE}/auth/google"
API_GOOGLE_POLL = f"{API_BASE}/auth/google/poll"
API_VERIFY = f"{API_BASE}/auth/verify"
API_JOIN_ORG   = f"{API_BASE}/org/join"
API_CREATE_ORG = f"{API_BASE}/org/create"
API_QUOTA      = f"{API_BASE}/quota/"
API_QUOTA_LOG  = f"{API_BASE}/quota/log/"

BILLING_URL = (
    os.getenv("POSTURE_BILLING_URL")
    or _RUNTIME_CONFIG.get("billing_url")
    or "http://localhost:3000/settings/billing"
)
DEV_MODE = _bool_from_any(
    os.getenv("POSTURE_DEV_MODE", _RUNTIME_CONFIG.get("dev_mode", False)),
    default=False,
)
DEMO_MODE = _bool_from_any(
    os.getenv("POSTURE_DEMO_MODE", _RUNTIME_CONFIG.get("demo_mode", DEV_MODE)),
    default=False,
)

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

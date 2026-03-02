"""mock_api.py — Simple Flask-based mock API for local development.

Run with: python mock_api.py

Provides endpoints under /api/v1/auth and /api/v1/org that mirror the app's expected
contract. This is intentionally minimal and not secure — for local development
only.
"""
from datetime import datetime, timedelta, timezone
from functools import wraps
import json

from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory token store: token -> expires_at ISO
TOKENS = {}
OAUTH_SESSIONS = {}

DEMO_EMAIL = "demo@local"
DEMO_PASS = "demo1234"

# helper
def make_token(email: str) -> str:
    token = f"token-{email}-{int(datetime.now(timezone.utc).timestamp())}"
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    TOKENS[token] = expires
    return token, expires


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "missing token"}), 401
        token = auth.split(" ", 1)[1]
        exp = TOKENS.get(token)
        if not exp:
            return jsonify({"error": "invalid token"}), 401
        try:
            if datetime.fromisoformat(exp) <= datetime.now(timezone.utc):
                return jsonify({"error": "expired"}), 401
        except Exception:
            return jsonify({"error": "invalid expiry"}), 401
        return fn(*args, **kwargs)
    return wrapper


@app.route("/api/v1/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = data.get("email")
    password = data.get("password")
    if not email or "@" not in email:
        return jsonify({"error": "invalid_email"}), 400
    if not password or len(password) < 4:
        return jsonify({"error": "invalid_password"}), 400

    # Accept demo creds or any email/pass for dev
    if email == DEMO_EMAIL and password == DEMO_PASS:
        token, expires = make_token(email)
        return jsonify({
            "email": email,
            "name": "Demo User",
            "plan": "Solo",
            "first_time": False,
            "token": token,
            "token_type": "Bearer",
            "scope": "openid profile email",
            "refresh_token": f"refresh-{email}-{int(datetime.now(timezone.utc).timestamp())}",
            "expires_at": expires,
            "subscription": {
                "plan": "Solo",
                "status": "active",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
                "features": ["posture_tracking", "reports", "notifications"],
            },
        }), 200

    # generic success
    token, expires = make_token(email)
    return jsonify({
        "email": email,
        "name": email.split("@")[0].title(),
        "plan": "Enterprise",
        "first_time": True,
        "token": token,
        "token_type": "Bearer",
        "scope": "openid profile email",
        "refresh_token": f"refresh-{email}-{int(datetime.now(timezone.utc).timestamp())}",
        "expires_at": expires,
        "subscription": {
            "plan": "Enterprise",
            "status": "active",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        },
    }), 201


@app.route("/api/v1/auth/verify", methods=["GET"])
def verify():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "missing token"}), 401
    token = auth.split(" ", 1)[1]
    exp = TOKENS.get(token)
    if not exp:
        return jsonify({"error": "invalid token"}), 401
    try:
        if datetime.fromisoformat(exp) <= datetime.now(timezone.utc):
            return jsonify({"error": "expired"}), 401
    except Exception:
        return jsonify({"error": "invalid expiry"}), 401
    return jsonify({"status": "ok", "expires_at": exp}), 200


@app.route("/api/v1/auth/google", methods=["GET"])
def google_oauth():
    # Create a short-lived OAuth session and return a local URL the user can open.
    import uuid
    session_id = str(uuid.uuid4())
    # The URL points to a local completion endpoint which simulates the provider
    complete_url = f"http://localhost:8000/api/v1/auth/google/complete?session={session_id}"
    OAUTH_SESSIONS[session_id] = {"status": "pending", "token": None, "expires": None}
    return jsonify({"url": complete_url, "session": session_id}), 200


@app.route("/api/v1/auth/google/complete", methods=["GET"])
def google_complete():
    # Simulate the end-user completing OAuth in the browser: mark session done and create token
    session = request.args.get("session")
    if not session or session not in OAUTH_SESSIONS:
        return "Invalid session.", 400
    token, expires = make_token("google_user@local")
    OAUTH_SESSIONS[session]["status"] = "done"
    OAUTH_SESSIONS[session]["token"] = token
    OAUTH_SESSIONS[session]["expires"] = expires
    # OAuth users are treated as new users with no active subscription
    OAUTH_SESSIONS[session]["subscription"] = {
        "plan": None,
        "status": "none",
        "expires_at": None,
    }
    # Simple HTML response the browser shows
    return f"<html><body><h2>OAuth complete</h2><p>You may now return to the application.</p></body></html>", 200


@app.route("/api/v1/auth/google/poll", methods=["GET"])
def google_poll():
    session = request.args.get("session")
    if not session or session not in OAUTH_SESSIONS:
        return jsonify({"status": "invalid"}), 400
    s = OAUTH_SESSIONS[session]
    if s["status"] == "pending":
        return jsonify({"status": "pending"}), 200
    return jsonify({
        "status": "done",
        "token": s["token"],
        "token_type": "Bearer",
        "scope": "openid profile email",
        "expires_at": s["expires"],
        "email": "google_user@local",
        "name": "Google User",
        "first_time": True,
        "subscription": s.get("subscription") or {"plan": None, "status": "none", "expires_at": None},
    }), 200


@app.route("/api/v1/auth/google/callback", methods=["GET"])
def google_callback():
    # Simulate exchange — accept ?code=... and return token
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "missing_code"}), 400
    # create token for demo
    token, expires = make_token("google_user@local")
    return jsonify({
        "token": token,
        "token_type": "Bearer",
        "scope": "openid profile email",
        "refresh_token": f"refresh-google-{int(datetime.now(timezone.utc).timestamp())}",
        "expires_at": expires,
        "email": "google_user@local",
        "name": "Google User",
        "subscription": {"plan": None, "status": "none", "expires_at": None},
    }), 200


@app.route("/api/v1/auth/signup", methods=["GET"])
def signup_form():
    # Simple signup page for local dev — clicking the link will create a token.
    example_email = request.args.get("email", "newuser@local")
    complete_url = f"http://localhost:8000/api/v1/auth/signup/complete?email={example_email}"
    return f"<html><body><h2>Sign up (mock)</h2><p>Click to complete signup for <b>{example_email}</b>:</p><p><a href=\"{complete_url}\">Complete signup</a></p></body></html>", 200


@app.route("/api/v1/auth/signup/complete", methods=["GET"])
def signup_complete():
    email = request.args.get("email") or "newuser@local"
    token, expires = make_token(email)
    return jsonify({
        "email": email,
        "name": email.split("@")[0].title(),
        "token": token,
        "token_type": "Bearer",
        "scope": "openid profile email",
        "expires_at": expires,
        "first_time": True,
        "subscription": {"plan": None, "status": "none", "expires_at": None},
    }), 200


@app.route("/api/v1/org/join", methods=["POST"])
@require_auth
def org_join():
    data = request.get_json(force=True)
    code = data.get("invite_code")
    if not code:
        return jsonify({"error": "missing_code"}), 400
    return jsonify({"status": "joined", "org_id": "org-123", "name": "Demo Org"}), 200


@app.route("/api/v1/org/create", methods=["POST"])
@require_auth
def org_create():
    data = request.get_json(force=True)
    name = data.get("org_name") or "New Workspace"
    return jsonify({"status": "created", "org_id": "org-456", "name": name}), 201


if __name__ == "__main__":
    print("Starting mock API on http://127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000)

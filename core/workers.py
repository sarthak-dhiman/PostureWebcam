"""
workers.py — QThread workers for network-bound operations.

Every request runs off the main thread so the UI never freezes.
"""

import time
import json
import os
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject

from core.constants import (
    SUBSCRIPTION_CHECK_INTERVAL_MS,
    API_VERIFY,
    API_LOGIN,
    API_GOOGLE_OAUTH,
    API_GOOGLE_POLL,
)


# ── Mock local JWT store ────────────────────────────────────────────────────
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JWT_CACHE = os.path.join(_APP_DIR, "data", "jwt_cache.json")
_AUTH_CACHE = os.path.join(_APP_DIR, "data", "auth_cache.json")


def _read_local_jwt_expiry() -> str | None:
    """Read mock cached JWT expiry date from disk.  Returns ISO string or None."""
    try:
        with open(_JWT_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("expires_at")
    except Exception:
        return None


def _write_local_jwt_expiry(expiry_iso: str) -> None:
    """Persist a mock JWT expiry to disk."""
    os.makedirs(os.path.dirname(_JWT_CACHE), exist_ok=True)
    with open(_JWT_CACHE, "w", encoding="utf-8") as f:
        json.dump({"expires_at": expiry_iso}, f)


def _read_local_auth() -> dict | None:
    """Return cached auth payload (user dict) or None."""
    try:
        with open(_AUTH_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_local_auth(payload: dict) -> None:
    """Persist a simple auth payload to disk."""
    os.makedirs(os.path.dirname(_AUTH_CACHE), exist_ok=True)
    with open(_AUTH_CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _clear_local_auth() -> None:
    """Delete the auth cache so the next launch shows the login page."""
    try:
        if os.path.exists(_AUTH_CACHE):
            os.remove(_AUTH_CACHE)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  LoginWorker
# ─────────────────────────────────────────────────────────────────────────────

class LoginWorker(QThread):
    """Simulates a login network request on a background thread.

    Signals
    -------
    login_success(dict)   – user payload on success
    login_failed(str)     – error message on failure
    """

    login_success = pyqtSignal(dict)
    login_failed = pyqtSignal(str)

    def __init__(self, email: str, password: str, parent=None):
        super().__init__(parent)
        self._email = email
        self._password = password

    def run(self):
        try:
            if not self._email or "@" not in self._email:
                self.login_failed.emit("Please enter a valid email address.")
                return
            if len(self._password) < 4:
                self.login_failed.emit("Password must be at least 4 characters.")
                return

            import urllib.request
            import urllib.error

            payload = json.dumps({"email": self._email, "password": self._password}).encode("utf-8")
            req = urllib.request.Request(API_LOGIN, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status in (200, 201):
                        body = json.load(resp)
                        user = {
                            "email": body.get("email", self._email),
                            "name": body.get("name", self._email.split("@")[0].title()),
                            "plan": body.get("plan", "—"),
                            "first_time": body.get("first_time", False),
                            "token": body.get("token"),
                            "expires_at": body.get("expires_at"),
                            "subscription": body.get("subscription") or {},
                        }
                        _write_local_jwt_expiry(user["expires_at"])
                        _write_local_auth(user)
                        self.login_success.emit(user)
                    else:
                        self.login_failed.emit(f"Login failed (HTTP {resp.status}).")
            except urllib.error.HTTPError as e:
                # Server responded with 4xx/5xx — do NOT fall back
                try:
                    body = json.load(e)
                    msg = body.get("error") or body.get("message") or f"HTTP {e.code}"
                except Exception:
                    msg = f"HTTP {e.code}: {e.reason}"
                self.login_failed.emit(msg)
            except urllib.error.URLError as e:
                # Genuine network failure (server down, DNS, timeout)
                self.login_failed.emit("Cannot reach the server. Please check your connection.")

        except Exception as exc:
            self.login_failed.emit(f"Unexpected error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
#  SubscriptionMonitor
# ─────────────────────────────────────────────────────────────────────────────

class SubscriptionMonitor(QThread):
    """Runs at startup and every 12 h to verify the subscription status.

    Signals
    -------
    status_changed(str, str)
        (status, detail)
        status  – "online" | "offline" | "expired"
        detail  – human-readable info string
    """

    status_changed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    # ── public control ──────────────────────────────────────────────────
    def stop(self):
        self._running = False

    # ── thread body ─────────────────────────────────────────────────────
    def run(self):
        while self._running:
            self._check()
            # Sleep in small increments so we can exit quickly
            elapsed = 0
            while elapsed < SUBSCRIPTION_CHECK_INTERVAL_MS and self._running:
                self.msleep(500)
                elapsed += 500

    def _check(self):
        """Verify subscription against the backend. No local fallback."""
        import urllib.request
        import urllib.error

        _cached = _read_local_auth()
        _stored_token = (_cached or {}).get("token")

        if not _stored_token:
            self.status_changed.emit("expired", "Not logged in.")
            return

        try:
            req = urllib.request.Request(API_VERIFY, method="GET")
            req.add_header("Authorization", f"Bearer {_stored_token}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    self.status_changed.emit("online", "Subscription active — verified online.")
                else:
                    self.status_changed.emit("expired", f"Subscription check failed (HTTP {resp.status}).")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                self.status_changed.emit("expired", "Session expired. Please log in again.")
            else:
                self.status_changed.emit("expired", f"Subscription check failed (HTTP {e.code}).")
        except urllib.error.URLError:
            self.status_changed.emit("offline", "Cannot reach server — working offline.")
        except Exception as exc:
            self.status_changed.emit("offline", f"Subscription check error: {exc}")



# ─────────────────────────────────────────────────────────────────────────────
#  OAuthInitWorker
# ─────────────────────────────────────────────────────────────────────────────


class OAuthInitWorker(QThread):
    """Background thread that requests the OAuth provider URL from the backend.

    Signals
    -------
    init_success(str, str)  – (provider_url, session_id) on success
    init_failed(str)        – error message on failure
    """

    init_success = pyqtSignal(str, str)
    init_failed  = pyqtSignal(str)

    def run(self):
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(API_GOOGLE_OAUTH, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.load(resp)
                url     = body.get("url")
                session = body.get("session")
                if not url or not session:
                    self.init_failed.emit("Invalid OAuth response from server.")
                    return
                self.init_success.emit(url, session)
        except urllib.error.HTTPError as e:
            try:
                body = json.load(e)
                msg = body.get("error") or body.get("message") or f"HTTP {e.code}"
            except Exception:
                msg = f"HTTP {e.code}: {e.reason}"
            self.init_failed.emit(f"Failed to start OAuth: {msg}")
        except urllib.error.URLError:
            self.init_failed.emit("Cannot reach the server. Please check your connection.")
        except Exception as exc:
            self.init_failed.emit(f"Unexpected error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
#  OAuthPollWorker
# ─────────────────────────────────────────────────────────────────────────────


class OAuthPollWorker(QThread):
    """Polls the backend for OAuth completion using a session token.

    Signals
    -------
    oauth_success(dict) – emitted with the user payload when token available
    oauth_failed(str)   – emitted with an error message on timeout/failure
    """

    oauth_success = pyqtSignal(dict)
    oauth_failed = pyqtSignal(str)

    def __init__(self, session_id: str, timeout_s: int = 60, parent=None):
        super().__init__(parent)
        self._session = session_id
        self._timeout = timeout_s
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            import urllib.request
            import urllib.error

            start = time.time()
            while self._running and (time.time() - start) < self._timeout:
                try:
                    url = f"{API_GOOGLE_POLL}?session={self._session}"
                    with urllib.request.urlopen(url, timeout=5) as resp:
                        if resp.status == 200:
                            body = json.load(resp)
                            if body.get("status") == "done":
                                sub = body.get("subscription") or {}
                                user = {
                                    "email": body.get("email"),
                                    "name": body.get("name"),
                                    "token": body.get("token"),
                                    "expires_at": body.get("expires_at"),
                                    "first_time": body.get("first_time", True),
                                    "plan": (sub.get("plan") or "None"),
                                    "subscription": sub,
                                }
                                # persist to disk so app can auto-login
                                _write_local_jwt_expiry(user.get("expires_at", ""))
                                _write_local_auth(user)
                                self.oauth_success.emit(user)
                                return
                except urllib.error.URLError:
                    pass
                except Exception:
                    pass

                # Sleep a short while before polling again
                self.msleep(1000)

            if not self._running:
                self.oauth_failed.emit("Cancelled")
            else:
                self.oauth_failed.emit("OAuth timed out")

        except Exception as exc:
            self.oauth_failed.emit(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
#  PostureTrackerThread
# ─────────────────────────────────────────────────────────────────────────────


class PostureTrackerThread(QThread):
    """Background posture tracker thread.

    - Emits `posture_update(dict)` periodically with the latest posture stats.
    - Can be placed on hold via `set_hold(True)` to pause processing when
      the subscription is not active.
    - Provides `start_capture()` and `shutdown()` control methods.
    """

    posture_update = pyqtSignal(dict)
    status_changed = pyqtSignal(str, str)

    def __init__(self, poll_interval_ms: int = 500, spawn_daemon: bool = True, parent=None):
        super().__init__(parent)
        self._running = True
        self._hold = True
        self._interval = max(100, int(poll_interval_ms))
        self._spawn_daemon_enabled = spawn_daemon
        self._daemon_proc = None   # subprocess.Popen handle for tracker_daemon.py
        # live stats path (same location used by system_tray_widget)
        from pathlib import Path
        self._base = Path(__file__).resolve().parents[1]
        self._live_stats = self._base / "live_stats.json"

    # ------------------------------------------------------------------
    # daemon process helpers
    # ------------------------------------------------------------------
    def _kill_daemon(self):
        """Terminate tracker_daemon.py subprocess if it is running."""
        _pid_file = str(self._base / "data" / "tracker_daemon.pid")
        proc = self._daemon_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._daemon_proc = None
        # Remove PID file so the next spawn does not try to kill a stale PID
        try:
            if os.path.exists(_pid_file):
                os.remove(_pid_file)
        except Exception:
            pass

    def _spawn_daemon(self):
        """Start tracker_daemon.py as a detached subprocess (no console window)."""
        if not self._spawn_daemon_enabled:
            return
        import subprocess, sys
        if self._daemon_proc is not None and self._daemon_proc.poll() is None:
            return  # already running
        daemon_script = str(self._base / "tracker_daemon.py")
        _pid_file = str(self._base / "data" / "tracker_daemon.pid")

        # Kill any orphaned daemon process left over from a previous session
        try:
            if os.path.exists(_pid_file):
                with open(_pid_file, "r", encoding="utf-8") as _pf:
                    _old_pid = int(_pf.read().strip())
                try:
                    if sys.platform == "win32":
                        import ctypes
                        _hnd = ctypes.windll.kernel32.OpenProcess(1, False, _old_pid)
                        if _hnd:
                            ctypes.windll.kernel32.TerminateProcess(_hnd, 1)
                            ctypes.windll.kernel32.CloseHandle(_hnd)
                    else:
                        os.kill(_old_pid, 9)
                except Exception:
                    pass
                try:
                    os.remove(_pid_file)
                except Exception:
                    pass
        except Exception:
            pass

        # On Windows hide the console window so no black Python terminal pops up
        _popen_kwargs: dict = {"cwd": str(self._base)}
        if sys.platform == "win32":
            _popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        # In a frozen (PyInstaller --onedir) build tracker_daemon.py is compiled
        # to tracker_daemon.exe in the same directory as the main executable.
        # When running from source, use the Python interpreter + .py script as usual.
        if getattr(sys, "frozen", False):
            _exe_dir = os.path.dirname(sys.executable)
            _daemon_exe = os.path.join(_exe_dir, "tracker_daemon.exe")
            _cmd = [_daemon_exe, "--no-tray"]
        else:
            _cmd = [sys.executable, daemon_script, "--no-tray"]

        try:
            proc = subprocess.Popen(
                _cmd,
                **_popen_kwargs,
            )
            self._daemon_proc = proc
            # Persist PID so it can be killed if the app exits unexpectedly
            try:
                os.makedirs(os.path.dirname(_pid_file), exist_ok=True)
                with open(_pid_file, "w", encoding="utf-8") as _pf:
                    _pf.write(str(proc.pid))
            except Exception:
                pass
        except Exception as e:
            print(f"[PostureTrackerThread] Failed to spawn tracker_daemon: {e}")

    def ensure_daemon_running(self) -> None:
        """Public helper to ensure the tracker daemon subprocess is running.

        This will start the daemon if `spawn_daemon` is enabled and no daemon
        process is currently active. It does not change the tracker's hold
        state or begin capturing; it merely ensures the background daemon is
        alive so the dashboard can read live stats immediately.
        """
        try:
            self._spawn_daemon()
        except Exception:
            pass

    # ------------------------------------------------------------------

    def set_hold(self, hold: bool):
        """Toggle hold state. When on hold the tracker emits a 'no_tracker'
        status and pauses reading captures."""
        self._hold = bool(hold)
        if self._hold:
            self._kill_daemon()
            # notify UI that tracker is idle due to subscription/hold
            self.status_changed.emit("hold", "Tracker paused (subscription hold)")

    def start_capture(self):
        """Bring the tracker out of hold and begin capturing (non-blocking)."""
        # Delete stale live_stats.json so the worker doesn't show last-session
        # data while the fresh daemon is booting up.
        try:
            if self._live_stats.exists():
                self._live_stats.unlink()
        except Exception:
            pass
        self._spawn_daemon()
        self._hold = False
        self.status_changed.emit("running", "Tracker running")

    def shutdown(self):
        self._kill_daemon()
        self._running = False

    def run(self):
        import json
        import time

        while self._running:
            if self._hold:
                # when held, emit periodic idle status so UI can show "no_tracker"
                self.posture_update.emit({
                    "label": "no_tracker",
                    "reason": "hold",
                    "body_detected": False,
                })
                # sleep a bit while on hold
                self.msleep(500)
                continue

            # Not on hold: try to read live stats file if present
            try:
                if self._live_stats.exists():
                    with open(self._live_stats, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # normalize payload — daemon can write label=None when no body
                    label = data.get("label") or "no_body"
                    reason = data.get("reason", "")
                    body = data.get("body_detected", True)
                    # Prefer aggregate bad_streak from daemon if available;
                    # otherwise fall back to max of per-issue streak counters.
                    bad_streak_sec = data.get("bad_streak")
                    if bad_streak_sec is None:
                        bad_streak_sec = max(
                            data.get("chin_streak", 0) or 0,
                            data.get("shoulder_streak", 0) or 0,
                            data.get("head_tilt_streak", 0) or 0,
                            data.get("lean_back_streak", 0) or 0,
                        )
                    payload = {
                        "label": label,
                        "reason": reason,
                        "body_detected": body,
                        "confidence": data.get("confidence"),
                        "dist_cm": data.get("dist_cm"),
                        "head_tilt_deg": data.get("head_tilt_deg"),
                        "sit_elapsed_sec": data.get("sit_elapsed_sec", 0) or 0,
                        "eye_elapsed_sec": data.get("eye_elapsed_sec", 0) or 0,
                        "bad_streak_sec":  bad_streak_sec,
                    }
                    self.posture_update.emit(payload)
                else:
                    # no live stats yet — emit no_tracker
                    self.posture_update.emit({
                        "label": "no_tracker",
                        "reason": "no_data",
                        "body_detected": False,
                    })
            except Exception:
                # on error, emit unknown/error
                self.posture_update.emit({
                    "label": "error",
                    "reason": "read_error",
                    "body_detected": False,
                })

            # sleep between polls
            self.msleep(self._interval)

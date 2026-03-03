# Posture Webcam Analyzer

A Windows desktop application that uses your webcam to monitor your sitting posture in real time, alert you when you slouch, track long-term trends, and generate detailed reports — all backed by a subscription-gated web API.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Posture Detection Pipeline](#posture-detection-pipeline)
6. [Website / API Integration](#website--api-integration)
7. [Local Database](#local-database)
8. [GUI Application](#gui-application)
9. [System Tray Daemon](#system-tray-daemon)
10. [Reports](#reports)
11. [Getting Started](#getting-started)
12. [Configuration](#configuration)
13. [Development Notes](#development-notes)

---

## Overview

The app runs as a **headless background daemon** (system tray) that continuously monitors your posture via webcam at approximately 1 FPS. A separate **PyQt6 GUI** provides a dashboard, historical charts, report generation, and account management. Access to the app is gated behind an online account — the desktop client authenticates with a REST API and verifies an active subscription every 12 hours.

Key capabilities:

- Real-time posture classification (good/bad) using a two-stage pipeline: ONNX neural network → geometry heuristics fallback
- Identity lock via face recognition — only tracks the registered owner
- Sitting distance estimation using a pinhole camera model
- Forward-head angle measurement (degrees), shoulder roll, lateral head tilt, and lean-back detection
- Configurable desktop notifications and sound alerts
- SQLite logging of every posture observation
- Daily/monthly PDF and text reports with charts
- Live MJPEG camera stream served on `localhost:8765` for the dashboard preview
- System tray widget with real-time status indicator

---

## Architecture

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│   tracker_daemon.py     │        │      app_window.py (GUI)     │
│  ─────────────────────  │        │  ──────────────────────────  │
│  Main thread: pystray   │        │  PyQt6 QStackedWidget        │
│  Worker thread:         │◄──────►│  ├── LoginPage               │
│   Camera → MediaPipe    │        │  ├── JoinOrgPage             │
│   → Face recognition    │        │  ├── DashboardPage           │
│   → ONNX classifier     │        │  ├── ReportsPage             │
│   → Heuristics fallback │        │  └── AccountPage             │
│   → SQLite write        │        │                              │
│   → live_stats.json     │        │  Sidebar + subscription LED  │
│   → MJPEG stream :8765  │        └──────────────────────────────┘
└─────────────────────────┘                     │
             │                                  │ HTTP (urllib)
             │ live_stats.json                  ▼
             │                    ┌──────────────────────────────┐
             └───────────────────►│   Backend REST API           │
                                  │   (mock: localhost:8000)     │
                                  │   POST /api/v1/auth/login    │
                                  │   GET  /api/v1/auth/verify   │
                                  │   GET  /api/v1/auth/google   │
                                  │   POST /api/v1/org/join      │
                                  │   POST /api/v1/org/create    │
                                  └──────────────────────────────┘
```

The daemon and GUI are **independent processes**. The GUI reads `live_stats.json` written by the daemon, and both interact with the same SQLite database (`posture.db`).

---

## Tech Stack

| Layer | Library |
|-------|---------|
| Pose landmark detection | **MediaPipe Pose** (Google) — `pose_landmarker_lite.task` / `pose_landmarker_full.task` |
| Posture classifier | **ONNX Runtime** — custom MLP (`posture.onnx`) |
| Face recognition / identity lock | **face_recognition** (dlib) |
| Camera capture | **OpenCV** (`cv2`) |
| GUI | **PyQt6** |
| System tray | **pystray** + **Pillow** |
| Desktop notifications | **plyer** |
| Charts & reports | **matplotlib**, **plotly** |
| Local storage | **SQLite3** (`posture.db`) |
| HTTP client (API calls) | Python `urllib` (stdlib) |
| Mock API server | **Flask** (`mock_api.py`) |
| Packaging | **PyInstaller** (`PostureApp.spec`) |

Python version: **3.10** (venv at `venv310/`)

---

## Project Structure

```
Posture App/
│
├── main.py                  # Entry point — launches GUI + daemon subprocess
├── app_window.py            # Root QMainWindow, page stack, auth orchestration
├── tracker_daemon.py        # Headless tracking daemon (system tray + camera loop)
├── database.py              # SQLite schema and insert/query helpers
├── report_generator.py      # Daily/monthly PDF + text report generation
├── mock_api.py              # Local Flask mock of the production REST API
├── camera_perms.py          # Windows camera permission check helper
├── system_tray_widget.py    # Standalone tray widget (alternative launcher)
├── build_executable.py      # Helper to invoke PyInstaller
├── PostureApp.spec          # PyInstaller spec file
│
├── core/
│   ├── constants.py         # API URLs, app name, timing constants
│   ├── workers.py           # QThread workers: LoginWorker, SubscriptionMonitor, OAuthInitWorker
│   ├── icons.py             # SVG/icon helpers
│   └── stylesheet.py        # Global Qt stylesheet (dark theme)
│
├── views/
│   ├── login_page.py        # Login form + Google OAuth button
│   ├── join_org_page.py     # Organisation invite-code page
│   ├── dashboard_page.py    # Live posture feed, KPI cards, distance gauge
│   ├── reports_page.py      # Historical charts and report export
│   ├── account_page.py      # Subscription status, billing link, logout
│   └── user_settings_page.py
│
├── widgets/
│   ├── sidebar.py           # Navigation sidebar with subscription LED
│   ├── dial_widget.py       # Circular dial (distance / angle display)
│   └── kpi_card.py          # Summary metric card
│
├── data/
│   ├── app_config.json      # User preferences (alert timing, sound, notifications)
│   ├── auth_cache.json      # Cached JWT token and user info (written on login)
│   ├── jwt_cache.json       # JWT expiry cache
│   └── distance_calibration.json  # Focal-length calibration for distance estimate
│
├── live_stats.json          # IPC file: daemon → GUI (posture label, angle, distance)
├── posture.db               # SQLite database (auto-created)
├── owner.jpg                # Reference face image for identity lock
├── pose_landmarker_lite.task   # MediaPipe Tasks model (lite variant)
├── pose_landmarker_full.task   # MediaPipe Tasks model (full variant)
└── requirements.txt
```

---

## Posture Detection Pipeline

Every camera frame goes through a multi-stage pipeline:

### Stage 1 — MediaPipe Pose

OpenCV grabs a frame from the webcam. MediaPipe Pose returns **33 body landmarks**, each with normalised `(x, y, z)` coordinates in [0, 1] image space.

Two API variants are supported transparently:
- `mediapipe.solutions.pose` — classic API
- `mediapipe.tasks.python.vision` — newer Tasks API (uses the `.task` model files)

Key landmarks used downstream:

| Index | Body part |
|-------|-----------|
| 0 | Nose |
| 7, 8 | Left / Right Ear |
| 11, 12 | Left / Right Shoulder |
| 23, 24 | Left / Right Hip |
| 25–28 | Knees & Ankles |

---

### Stage 2 — Identity Lock (face_recognition / dlib)

Before any posture analysis, the frame is checked against the registered owner face (`owner.jpg`). A 128-dimensional face encoding is compared with tolerance `0.6`. If the person is not the owner, the frame is skipped entirely and nothing is written to the database.

---

### Stage 3 — ONNX Neural Network Classifier (primary)

**Model:** `posture.onnx` — a small MLP trained on MMPose-style data.

**Feature vector (24 floats):**
```
[ nose_x, nose_y,
  mid_shoulder_x, mid_shoulder_y,
  mid_hip_x,      mid_hip_y,
  mid_knee_x,     mid_knee_y,
  mid_ankle_x,    mid_ankle_y,
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 ]  ← 14 zero-padded
```

Output: softmax over `[Good, Bad]`. If confidence ≥ `0.65` (`ONNX_CONF_THRESHOLD`), the label is accepted. Otherwise the heuristic fallback runs.

---

### Stage 4 — Geometry Heuristics Fallback

Six independent checks, all using normalised coordinates divided by shoulder width (making them camera-distance-independent):

| Check | Signal | Threshold |
|-------|--------|-----------|
| **Forward-head / neck drop** | `(shoulder_y − ear_y) / shoulder_width` | < `0.45` |
| **Shoulder asymmetry (Y)** | `|left_sho_y − right_sho_y| / shoulder_width` | > `0.18` |
| **Shoulder roll (tilt angle)** | `atan2(Δy, Δx)` of shoulder line | > `8.0°` |
| **Shoulder depth asymmetry (Z)** | `|left_sho_z − right_sho_z|` | > `0.06` |
| **Lateral head tilt** | Ear-to-ear line angle | > `12.0°` |
| **Torso lean-back** | `mid_shoulder_z − mid_hip_z` | > `0.10` |

Any single flag → `bad` posture. Additionally:

- **Chin-forward (Z-axis):** `mid_shoulder_z − nose_z > CHIN_FORWARD_Z_THRESHOLD` flags head protrusion.
- **Forward-head angle override:** If the estimated forward-head angle ≤ 3°, the verdict is forced to `good`.
- **Head tilt override:** A flagged lateral tilt always overrides a `good` verdict back to `bad`.

---

### Stage 5 — Forward-Head Angle Estimation

Computed independently of the classifier (stored in the DB and shown on the dashboard):

$$\text{fwd\_angle} = \text{clamp}\!\left((R_{ref} - R_{current}) \times 75,\; 0°,\; 45°\right)$$

Where $R_{ref}$ is the ear-to-shoulder ratio captured once at first owner verification (calibrated per session), and $R_{current}$ is the ratio for the current frame.

---

### Stage 6 — Temporal Smoothing

A sliding deque of the last **3 frames** (`LABEL_SMOOTH_WINDOW`) takes a **majority vote** between `good` / `bad` labels to suppress per-frame noise before the final verdict is committed.

---

### Stage 7 — Sitting Distance Estimation

Uses the **pinhole camera model**:

$$\text{distance\_cm} = \frac{\text{real\_shoulder\_width\_cm} \times \text{focal\_px}}{\text{shoulder\_px}}$$

The focal length is loaded from `data/distance_calibration.json` each frame so the "Calibrate" button in the dashboard takes effect without restart.

---

## Website / API Integration

The desktop app is designed to work against a production REST API. During development, `mock_api.py` (Flask, port `8000`) replicates the full contract.

### Base URL

```
Development:  http://localhost:8000/api/v1
Production:   set API_BASE in core/constants.py
```

### Authentication Flow

#### Email / Password Login

```
GUI (LoginPage)
  │
  └─► POST /api/v1/auth/login
        Body: { "email": "...", "password": "..." }
        ◄── { "token", "email", "name", "plan", "subscription", "expires_at", ... }
              │
              └─ token saved to data/auth_cache.json
                 GUI navigates to Dashboard or JoinOrg (if first_time=true)
```

#### Google OAuth (browser-based)

```
GUI
  │
  └─► GET /api/v1/auth/google
        ◄── { "url": "<browser_url>", "session": "<session_id>" }
              │
              ├─ App opens URL in default browser
              │
              └─► GET /api/v1/auth/google/poll?session=<id>   (polls every 2 s)
                    ◄── { "status": "pending" | "done", "token": ..., ... }
                          └─ on "done": same auth cache write as password login
```

#### Subscription Verification

Runs in a background `QThread` (`SubscriptionMonitor`) every **12 hours**:

```
GET /api/v1/auth/verify
  Header: Authorization: Bearer <token>
  ◄── 200 { "status": "ok", "expires_at": "..." }   → sidebar LED = green "online"
  ◄── 401                                            → sidebar LED = red "expired"
  ◄── network error                                  → sidebar LED = orange "offline"
```

The JWT expiry is also cached locally in `data/jwt_cache.json` for offline grace periods.

#### Organisation / Team Features

```
POST /api/v1/org/join    Body: { "invite_code": "..." }
POST /api/v1/org/create  Body: { "org_name": "..." }
```

Both require a valid `Authorization: Bearer <token>` header.

### API Contract Summary

| Method | Endpoint | Auth required | Purpose |
|--------|----------|:---:|---------|
| `POST` | `/api/v1/auth/login` | ✗ | Email/password login |
| `GET` | `/api/v1/auth/verify` | ✓ | Verify token / subscription |
| `GET` | `/api/v1/auth/google` | ✗ | Start Google OAuth — returns browser URL |
| `GET` | `/api/v1/auth/google/poll` | ✗ | Poll OAuth completion |
| `GET` | `/api/v1/auth/google/callback` | ✗ | OAuth redirect handler |
| `GET` | `/api/v1/auth/signup` | ✗ | Signup page redirect |
| `GET` | `/api/v1/auth/signup/complete` | ✗ | Signup completion callback |
| `POST` | `/api/v1/org/join` | ✓ | Join an organisation by invite code |
| `POST` | `/api/v1/org/create` | ✓ | Create a new organisation |

### Token Storage

After a successful login the following is persisted to `data/auth_cache.json`:

```json
{
  "email": "user@example.com",
  "name": "User Name",
  "plan": "Solo",
  "token": "Bearer ...",
  "expires_at": "2026-12-31T00:00:00+00:00",
  "subscription": {
    "plan": "Solo",
    "status": "active",
    "expires_at": "..."
  }
}
```

On every app launch, if a valid cached token exists the app skips the login page and goes directly to the dashboard. The tracker daemon reads `auth_cache.json` to decide whether to record posture data.

### Billing / Subscription Management

Clicking **Manage Subscription** in the Account page opens `BILLING_URL` (defined in `core/constants.py`) in the system browser — this points to your billing portal (e.g. Stripe Customer Portal).

---

## Local Database

File: `posture.db` (SQLite, auto-created on first run)

**Schema:**
```sql
CREATE TABLE posture_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,   -- ISO-8601 UTC
    posture     TEXT    NOT NULL,   -- 'good' | 'bad'
    ear_y       REAL,               -- normalised Y of mid-ear
    shoulder_y  REAL,               -- normalised Y of mid-shoulder
    hip_y       REAL,               -- normalised Y of mid-hip
    fwd_angle   REAL,               -- estimated forward-head angle (degrees)
    is_owner    INTEGER NOT NULL DEFAULT 1
);
```

One row is written per tracking cycle (~1 second) when the owner is verified in frame. The reports module queries this table for daily/monthly aggregation.

---

## GUI Application

Built with **PyQt6**, using a `QStackedWidget` to switch between pages:

| Index | Page | Purpose |
|-------|------|---------|
| 0 | `LoginPage` | Email/password login + Google OAuth + signup link |
| 1 | `JoinOrgPage` | Enter an organisation invite code (shown on first login) |
| 2 | `DashboardPage` | Live posture feed, KPI cards, distance dial, MJPEG preview |
| 3 | `ReportsPage` | Historical charts (daily/monthly), export to PDF/text |
| 4 | `AccountPage` | Subscription status, billing link, log out |

The `Sidebar` widget shows the logged-in email, a subscription status LED (green/orange/red), and navigation buttons.

### Launching the GUI

```powershell
# Activate the venv
.\venv310\Scripts\Activate.ps1

# Start mock API (dev only)
python mock_api.py

# Launch GUI
python main.py
```

Or use the provided launcher:

```powershell
.\run_gui.ps1    # starts mock API if not running, then launches GUI
```

---

## System Tray Daemon

`tracker_daemon.py` runs independently as a system tray application. It:

1. Acquires the webcam via OpenCV
2. Spawns a worker thread running the posture loop at ~1 FPS
3. Writes `live_stats.json` after each frame for the GUI to read
4. Serves a **MJPEG stream** on `http://localhost:8765` for the dashboard camera preview
5. Fires desktop notifications via `plyer` when bad posture is sustained beyond the configured alert threshold

The tray icon changes colour:
- 🟢 Green — good posture
- 🔴 Red — bad posture
- ⚪ Grey — no person detected / tracker not running

---

## Reports

`report_generator.py` produces:

- **Daily reports** — posture breakdown, forward-head angle chart, good/bad ratio, worst periods
- **Monthly reports** — aggregated trends, per-day breakdown, average angles
- **Formats:** PDF (with embedded matplotlib charts) and plain text
- **Email delivery:** Configurable SMTP sender (requires production SMTP credentials — see `PLACEHOLDERS.md`)

Reports are saved to `data/reports/` and can be exported from the Reports page in the GUI.

---

## Getting Started

### Prerequisites

- Windows 10/11
- Python 3.10
- A webcam
- `owner.jpg` — a clear photo of your face placed in the project root

### Install dependencies

```powershell
python -m venv venv310
.\venv310\Scripts\Activate.ps1
pip install -r requirements.txt
```

> **Note:** `dlib` is included via `dlib-bin` (pre-compiled wheel). No Visual Studio Build Tools required.

### Run (development)

```powershell
# Terminal 1 — mock API
python mock_api.py

# Terminal 2 — GUI
python main.py
```

**Demo credentials** (mock API only):
```
Email:    demo@local
Password: demo1234
```

### Build executable

```powershell
python build_executable.py
# or
pyinstaller PostureApp.spec
```

Output: `dist/PostureApp/PostureApp.exe`

---

## Configuration

`data/app_config.json` — edited via the Settings button in the dashboard:

```json
{
  "alert_timing_seconds": 30,
  "notifications_enabled": true,
  "sound_enabled": true
}
```

`data/distance_calibration.json` — written by the "Calibrate Distance" flow in the dashboard:

```json
{
  "focal_px": 620.5
}
```

---

## Development Notes

### Replacing Placeholders for Production

See `PLACEHOLDERS.md` for the full list. Key items:

| File | What to change |
|------|---------------|
| `core/constants.py` line 10 | `API_BASE` → production API URL |
| `core/constants.py` line 18 | `BILLING_URL` → real billing portal |
| `views/login_page.py` line 121 | Signup redirect URL |
| `views/login_page.py` line 128 | Footer links (privacy, terms) |
| `report_generator.py` | SMTP host/port/credentials |
| `mock_api.py` | **Remove entirely from production builds** |

### MJPEG Stream

The daemon exposes `http://localhost:8765/` as a multipart MJPEG stream. The dashboard embeds this in a `QLabel` using `QNetworkAccessManager` for a live camera preview without blocking the GUI thread.

### IPC: `live_stats.json`

The daemon writes this file atomically after each tracking cycle:

```json
{
  "posture": "good",
  "fwd_angle": 4.2,
  "distance_cm": 68,
  "timestamp": "2026-03-03T10:22:01+00:00"
}
```

The dashboard polls this file every second to update the KPI cards.

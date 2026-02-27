"""
report_generator.py — Daily posture PDF report builder + delivery helpers.

Dependencies (install once):
    pip install fpdf2

Usage:
    from report_generator import generate_pdf, send_email, share_whatsapp_web
    pdf_path = generate_pdf("2026-02-26")
    send_email(pdf_path, "me@gmail.com", smtp_host="smtp.gmail.com",
               smtp_port=587, smtp_user="me@gmail.com", smtp_pass="app-pw")
"""

from __future__ import annotations

import io
import json
import os
import smtplib
import subprocess
import urllib.parse
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import calendar
from typing import Optional

import matplotlib
matplotlib.use("Agg")   # headless – no GUI needed
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import database

# ---------------------------------------------------------------------------
# PDF text sanitizer (ASCII-safe for Helvetica)
# ---------------------------------------------------------------------------
def _pdf_safe(text: str) -> str:
    """Replace em-dash/en-dash with ASCII dash, and remove other non-ASCII chars."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("\u2014", "-")
            .replace("\u2013", "-")
            .replace("—", "-")
            .replace("–", "-")
            .encode("ascii", errors="ignore").decode("ascii")
    )

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_APP_DIR       = Path(__file__).parent
SNAPSHOTS_DIR  = _APP_DIR / "data" / "snapshots"
REPORTS_DIR    = _APP_DIR / "data" / "reports"
CONFIG_PATH    = _APP_DIR / "data" / "report_config.json"

ACCENT_GOOD = "#4CAF50"
ACCENT_BAD  = "#F44336"
ACCENT_BLUE = "#2196F3"

# ---------------------------------------------------------------------------
# Chart helpers (return raw PNG bytes)
# ---------------------------------------------------------------------------


def _fig_donut(good: int, bad: int) -> bytes:
    fig, ax = plt.subplots(figsize=(3.5, 3.5), facecolor="white")
    if good + bad == 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12)
        ax.axis('off')
    else:
        wedges, texts, autotexts = ax.pie(
            [good, bad],
            colors=[ACCENT_GOOD, ACCENT_BAD],
            autopct="%1.0f%%",
            wedgeprops={"width": 0.5, "linewidth": 2, "edgecolor": "white"},
            startangle=90,
        )
        # Make text more readable
        for t in texts + autotexts:
            t.set_fontsize(9)
            t.set_color("black" if t.get_text() != "" else "gray")
        ax.set_title("Good vs Bad Posture", fontsize=11, pad=15, fontweight='bold')
        ax.legend(["Good", "Bad"], loc="lower center", ncol=2, fontsize=8, frameon=False)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120, facecolor='white')
    plt.close(fig)
    return buf.getvalue()


def _fig_timeline(timestamps, postures) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 3), facecolor="white")
    buckets = [0] * 24
    for ts, pos in zip(timestamps, postures):
        if pos == "bad":
            buckets[ts.hour] += 1
    bar_colors = [ACCENT_BAD if b > 0 else "#d0d0d0" for b in buckets]
    ax.bar(range(24), buckets, color=bar_colors, width=0.7)
    ax.set_xlabel("Hour of Day", fontsize=9)
    ax.set_ylabel("Bad Posture Frames", fontsize=9)
    ax.set_title("Bad Posture by Hour", fontsize=11)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 2)], rotation=45, fontsize=7)
    ax.grid(axis="y", linewidth=0.5, linestyle="--", alpha=0.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    plt.close(fig)
    return buf.getvalue()


def _fig_angle(timestamps, angles) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 3), facecolor="white")
    valid = [(ts, a) for ts, a in zip(timestamps, angles) if a is not None]
    if valid:
        xs, ys = zip(*valid)
        ax.plot(xs, ys, color=ACCENT_BLUE, linewidth=1.4)
        ax.fill_between(xs, ys, alpha=0.15, color=ACCENT_BLUE)
        ax.axhline(15.0, color=ACCENT_BAD, linewidth=1, linestyle="--", label="Threshold 15°")
        ax.legend(fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate(rotation=30, ha="right")
    ax.set_xlabel("Time", fontsize=9)
    ax.set_ylabel("Angle (°)", fontsize=9)
    ax.set_title("Forward Head Angle Over Day", fontsize=11)
    ax.grid(linewidth=0.5, linestyle="--", alpha=0.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    plt.close(fig)
    return buf.getvalue()


def _fig_monthly_bars(day_scores: list) -> bytes:
    """Vertical bar chart of daily posture scores for a calendar month."""
    fig, ax = plt.subplots(figsize=(10, 3.5), facecolor="white")
    if not day_scores:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12, color="gray")
        ax.axis("off")
    else:
        labels = [d.split("-")[-1] for d, _ in day_scores]
        scores = [s for _, s in day_scores]
        bar_colors = [
            "#4CAF50" if s >= 75 else "#FF9800" if s >= 50 else "#F44336"
            for s in scores
        ]
        bars = ax.bar(range(len(scores)), scores, color=bar_colors, width=0.65,
                      edgecolor="white", linewidth=0.5)
        ax.set_ylim(0, 115)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=7)
        ax.set_xlabel("Day of Month", fontsize=9)
        ax.set_ylabel("Good Posture %", fontsize=9)
        ax.set_title("Daily Posture Scores", fontsize=11, fontweight="bold")
        ax.axhline(75, color="#4CAF50", linewidth=1, linestyle="--", alpha=0.5, label="Good (75%)")
        ax.axhline(50, color="#FF9800", linewidth=1, linestyle="--", alpha=0.5, label="Fair (50%)")
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(axis="y", linewidth=0.5, linestyle="--", alpha=0.4)
        for bar, s in zip(bars, scores):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.5,
                f"{s:.0f}",
                ha="center", va="bottom", fontsize=6, color="#333",
            )
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Health-risk analyser
# ---------------------------------------------------------------------------

# Each risk entry:
#   key          – internal identifier matching reason-string keywords
#   label        – display name
#   condition    – medical condition most associated with this issue
#   threshold    – (optional) numeric threshold for severity note
#   tips         – short corrective advice shown in the risk table
_RISK_CATALOGUE = [
    {
        "key": "fwd_angle_high",
        "label": "Forward Head Posture",
        "condition": "Cervical Spondylosis / Neck Pain",
        "icon": ">>",
        "tip": "Keep screen at eye level. Practice chin-tuck exercises daily.",
    },
    {
        "key": "ear_sho",
        "label": "Head Dropped (Low Ear-Shoulder)",
        "condition": "Cervical Strain / Tension Headaches",
        "icon": "v",
        "tip": "Raise your monitor height. Roll shoulders back and sit tall.",
    },
    {
        "key": "lean_back",
        "label": "Torso Recline / Leaning Back",
        "condition": "Lumbar Disc Compression / Lower Back Pain",
        "icon": "<",
        "tip": "Use lumbar support. Keep hips at 90-100 deg and lean slightly forward.",
    },
    {
        "key": "roll",
        "label": "Shoulder Roll / Tilt",
        "condition": "Rotator Cuff Imbalance / Shoulder Impingement",
        "icon": "~",
        "tip": "Level both shoulders periodically. Strengthen the weaker side.",
    },
    {
        "key": "asym",
        "label": "Shoulder Asymmetry",
        "condition": "Scoliosis Risk / Uneven Spinal Loading",
        "icon": "/",
        "tip": "Alternate mouse hand occasionally. Use a symmetric chair.",
    },
    {
        "key": "head_tilt",
        "label": "Lateral Head Tilt",
        "condition": "Cervicogenic Headaches / Neck Muscle Imbalance",
        "icon": "T",
        "tip": "Level your head consciously. Ear-to-shoulder stretches help.",
    },
    {
        "key": "depth_diff",
        "label": "Shoulder Depth Asymmetry",
        "condition": "Thoracic Outlet Syndrome / Nerve Compression",
        "icon": "d",
        "tip": "Sit squarely facing the monitor. Avoid twisting at the waist.",
    },
]

_SEVERITY_COLOURS = {
    "High":   (244,  67,  54),   # red
    "Medium": (255, 152,   0),   # amber
    "Low":    ( 76, 175,  80),   # green
}


def _analyse_risks(summary: dict, rows: list) -> list[dict]:
    """
    Return a list of risk dicts sorted by severity descending.
    Each dict: {label, condition, icon, tip, count, pct, severity, note}
    """
    total_bad = max(summary.get("bad", 1), 1)
    total     = max(summary.get("total", 1), 1)
    avg_angle = summary.get("avg_angle") or 0.0

    # Count keyword hits in the reason strings across all rows
    # reason is stored in live_stats, not in the DB — so estimate from data we have.
    # The DB has fwd_angle.  We also try to read the latest live_stats if it exists.
    issue_counts: dict[str, int] = defaultdict(int)

    for row in rows:
        if str(row["posture"]) != "bad":
            continue
        a = row["fwd_angle"]
        if a is not None and float(a) > 15.0:
            issue_counts["fwd_angle_high"] += 1
        # ear_sho, lean_back, roll, asym, head_tilt, depth_diff — estimated from
        # the bad-posture fraction when reason detail is unavailable in DB.

    # Try to enrich from live_stats reason history — best effort
    _live_stats_path = Path(__file__).parent / "data" / "live_stats.json"
    try:
        _ls = json.loads(_live_stats_path.read_text(encoding="utf-8"))
        _reason = (_ls.get("reason") or "").lower()
        for entry in _RISK_CATALOGUE:
            k = entry["key"]
            if k == "fwd_angle_high":
                continue
            if k.replace("_", " ") in _reason or k in _reason:
                issue_counts[k] = max(issue_counts[k], 1)
    except Exception:
        pass

    # Build risk rows
    results = []
    for entry in _RISK_CATALOGUE:
        k     = entry["key"]
        count = issue_counts.get(k, 0)

        if k == "fwd_angle_high":
            pct = round(count / total * 100, 1) if count else 0.0
            if avg_angle >= 20:
                severity = "High"
                note = f"Avg angle {avg_angle:.1f} deg — chronic risk zone"
            elif avg_angle >= 12:
                severity = "Medium"
                note = f"Avg angle {avg_angle:.1f} deg — watch closely"
            elif count > 0:
                severity = "Low"
                note = f"Occasional spikes ({count} frames)"
            else:
                continue   # no evidence — skip
        else:
            pct = round(count / total_bad * 100, 1) if count else 0.0
            if count == 0:
                # Estimate from overall bad-posture rate as a background risk
                bad_pct = summary.get("bad_pct", 0) or 0
                if bad_pct >= 60:
                    severity = "Medium"
                    note = "Likely contributor — detailed reason unavailable"
                    count = "—"
                    pct   = "—"
                elif bad_pct >= 30:
                    severity = "Low"
                    note = "Possible contributor — monitor over more sessions"
                    count = "—"
                    pct   = "—"
                else:
                    continue   # good session, skip low-confidence entry
            elif pct >= 40:
                severity = "High"
                note = f"Detected in {pct}% of bad frames"
            elif pct >= 15:
                severity = "Medium"
                note = f"Detected in {pct}% of bad frames"
            else:
                severity = "Low"
                note = f"Detected in {pct}% of bad frames"

        results.append({
            "label":     entry["label"],
            "condition": entry["condition"],
            "icon":      entry["icon"],
            "tip":       entry["tip"],
            "count":     count,
            "pct":       pct,
            "severity":  severity,
            "note":      note,
        })

    # Sort: High → Medium → Low
    order = {"High": 0, "Medium": 1, "Low": 2}
    results.sort(key=lambda r: order.get(r["severity"], 3))
    return results


# ---------------------------------------------------------------------------
# Shared PDF rendering helpers
# ---------------------------------------------------------------------------


def _render_risk_table(pdf, risks: list) -> None:
    """Render the health-risk table + verdict box into *pdf* at current Y position."""
    COL_W = [6, 52, 58, 20, 54]
    HDR   = ["", "Posture Issue", "Condition at Risk", "Severity", "Detail / Tip"]
    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    for w, h in zip(COL_W, HDR):
        pdf.cell(w, 7, _pdf_safe(h), border=0, fill=True, align="C")
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    for idx, risk in enumerate(risks):
        sev = risk["severity"]
        sr, sg, sb = _SEVERITY_COLOURS[sev]
        if idx % 2 == 0:
            pdf.set_fill_color(250, 250, 250)
        else:
            pdf.set_fill_color(242, 242, 242)
        row_y = pdf.get_y()
        tip_lines = len(risk["tip"]) // 48 + 1
        row_h = max(8, tip_lines * 5 + 3)
        pdf.rect(10, row_y, sum(COL_W), row_h, "F")
        pdf.set_fill_color(sr, sg, sb)
        pdf.rect(10, row_y, COL_W[0], row_h, "F")
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, row_y + (row_h - 5) / 2)
        pdf.cell(COL_W[0], 5, _pdf_safe(risk["icon"]), align="C")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(10 + COL_W[0], row_y + 1)
        pdf.cell(COL_W[1], row_h - 2, _pdf_safe(risk["label"]), align="L")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(140, 0, 0)
        pdf.set_xy(10 + COL_W[0] + COL_W[1], row_y + 1)
        pdf.cell(COL_W[2], row_h - 2, _pdf_safe(risk["condition"]), align="L")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(sr, sg, sb)
        pdf.set_text_color(255, 255, 255)
        bx = 10 + COL_W[0] + COL_W[1] + COL_W[2]
        pdf.rect(bx, row_y + 1, COL_W[3], row_h - 2, "F")
        pdf.set_xy(bx, row_y + (row_h - 5) / 2)
        pdf.cell(COL_W[3], 5, _pdf_safe(sev), align="C")
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(60, 60, 60)
        tx = 10 + sum(COL_W[:4])
        pdf.set_xy(tx + 1, row_y + 1)
        pdf.multi_cell(COL_W[4] - 2, 4, _pdf_safe(f"{risk['note']}\nTip: {risk['tip']}"))
        pdf.set_y(row_y + row_h + 1)

    pdf.ln(6)
    # Verdict box
    high_count = sum(1 for r in risks if r["severity"] == "High")
    if high_count >= 2:
        verdict_txt = "HIGH RISK: Multiple sustained bad-posture patterns detected. Consult a physiotherapist."
        vr, vg, vb  = 244, 67, 54
    elif high_count == 1:
        verdict_txt = "MODERATE RISK: One critical posture pattern flagged. Address the high-severity item above promptly."
        vr, vg, vb  = 255, 152, 0
    else:
        verdict_txt = "LOW RISK: No dominant bad-posture pattern detected. Keep up the good work!"
        vr, vg, vb  = 76, 175, 80
    pdf.set_fill_color(vr, vg, vb)
    pdf.rect(10, pdf.get_y(), 190, 12, "F")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(14, pdf.get_y() + 3)
    pdf.cell(182, 6, _pdf_safe(verdict_txt))
    pdf.set_text_color(0, 0, 0)


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------


def generate_pdf(date_str: str, output_path: Optional[str] = None) -> str:
    """
    Build a multi-page PDF daily report for *date_str* (e.g. '2026-02-26').
    Returns the absolute path to the written PDF.

    Requires fpdf2:  pip install fpdf2
    """
    try:
        from fpdf import FPDF  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "fpdf2 is required for PDF reports.  "
            "Install it with:  pip install fpdf2"
        ) from exc

    _label = f"Daily Report - {date_str}"
    _gen_time = datetime.now().strftime("%d %b %Y %H:%M")

    class _PosturePDF(FPDF):
        def footer(self):  # called automatically on each page
            self.set_y(-12)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(160, 160, 160)
            self.cell(
                0, 5,
                _pdf_safe(f"Posture Tracker  |  {_label}  |  Generated {_gen_time}  |  Page {self.page_no()}"),
                align="C",
            )
            self.set_text_color(0, 0, 0)

    # ── Load data ──────────────────────────────────────────────────────────
    summary = database.get_daily_summary(date_str)
    rows    = database.get_records_range(date_str, date_str)

    ts_list, pos_list, angle_list = [], [], []
    for row in rows:
        try:
            # Parse UTC timestamp and convert to local timezone for display
            ts_utc = datetime.fromisoformat(str(row["timestamp"])).replace(tzinfo=timezone.utc)
            ts_local = ts_utc.astimezone()
            ts_list.append(ts_local)
            pos_list.append(str(row["posture"]))
            a = row["fwd_angle"]
            angle_list.append(float(a) if a is not None else None)
        except Exception:
            pass

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = str(REPORTS_DIR / f"posture_report_{date_str}.pdf")

    # ── Render charts ─────────────────────────────────────────────────────
    donut_png    = _fig_donut(summary["good"], summary["bad"])
    timeline_png = _fig_timeline(ts_list, pos_list)
    angle_png    = _fig_angle(ts_list, angle_list)

    # ── Collect snapshot thumbnails (bad frames, up to 8) ─────────────────
    snapshot_paths: list[str] = []
    if SNAPSHOTS_DIR.exists():
        date_prefix = date_str.replace("-", "")   # "20260226"
        all_snaps = sorted(
            [
                f for f in SNAPSHOTS_DIR.iterdir()
                if f.suffix.lower() == ".jpg"
                and f.stem.startswith(date_prefix)
                and "_bad" in f.stem
            ],
            key=lambda p: p.stat().st_mtime,
        )
        if len(all_snaps) > 8:
            step = len(all_snaps) / 8
            all_snaps = [all_snaps[int(i * step)] for i in range(8)]
        snapshot_paths = [str(p) for p in all_snaps]

    # ── Build PDF ──────────────────────────────────────────────────────────
    pdf = _PosturePDF()
    pdf.set_auto_page_break(auto=True, margin=18)

    # ── Page 1: Summary ───────────────────────────────────────────────────
    pdf.add_page()

    # Header band
    pdf.set_fill_color(33, 150, 243)
    pdf.rect(0, 0, 210, 30, "F")
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 8)
    pdf.cell(0, 10, _pdf_safe("Posture Tracker - Daily Report"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(10, 20)
    human_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %d %B %Y")
    pdf.cell(0, 6, _pdf_safe(f"Date: {human_date}     Generated: {datetime.now().strftime('%H:%M')}"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # KPI boxes
    def _kpi_box(x: float, y: float, title: str, value: str, rgb: tuple) -> None:
        r, g, b = rgb
        pdf.set_fill_color(r, g, b)
        pdf.rect(x, y, 58, 22, "F")
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(230, 230, 230)
        pdf.set_xy(x + 3, y + 3)
        pdf.cell(52, 4, _pdf_safe(title.upper()))
        pdf.set_font("Helvetica", "B", 17)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(x + 3, y + 8)
        pdf.cell(52, 10, _pdf_safe(value))
        pdf.set_text_color(0, 0, 0)

    total_str = f"{summary['total_minutes']}m" if summary["total_minutes"] else f"{summary['total']}s"
    avg_str   = f"{summary['avg_angle']:.1f} deg" if summary["avg_angle"] is not None else "N/A"
    ph        = summary["peak_bad_hour"]
    peak_str  = f"{ph:02d}:xx" if ph is not None else "N/A"

    _kpi_box(10,  42, "Total Tracked",  total_str,               (33, 150, 243))
    _kpi_box(73,  42, "Good Posture",   f"{summary['good_pct']:.0f}%", (76, 175, 80))
    _kpi_box(136, 42, "Bad Posture",    f"{summary['bad_pct']:.0f}%",  (244, 67, 54))
    _kpi_box(10,  68, "Avg Angle",      avg_str,                 (103, 58, 183))
    _kpi_box(73,  68, "Peak Bad Hour",  peak_str,                (255, 152, 0))

    pdf.ln(52)

    # Donut chart (centred)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_safe("Session Overview"), ln=True)
    _tmp = io.BytesIO(donut_png)
    pdf.image(_tmp, x=65, w=80)
    pdf.ln(6)

    # Timeline chart
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_safe("Hourly Bad Posture Timeline"), ln=True)
    _tmp = io.BytesIO(timeline_png)
    pdf.image(_tmp, x=10, w=190)
    pdf.ln(4)

    # Angle chart
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_safe("Forward Head Angle"), ln=True)
    _tmp = io.BytesIO(angle_png)
    pdf.image(_tmp, x=10, w=190)

    # ── Page 2: Snapshots (optional) ──────────────────────────────────────
    if snapshot_paths:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 10, _pdf_safe("Bad Posture Snapshots"), ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, _pdf_safe("Representative frames where bad posture was detected (up to 8 samples):"), ln=True)
        pdf.ln(3)

        COLS      = 4
        THUMB_W   = 44.0
        THUMB_H   = 33.0
        GAP       = 3.0
        X_START   = 10.0
        row_y     = pdf.get_y()

        for i, sp in enumerate(snapshot_paths):
            col = i % COLS
            row = i // COLS
            x   = X_START + col * (THUMB_W + GAP)
            y   = row_y + row * (THUMB_H + GAP + 7)
            try:
                pdf.image(sp, x=x, y=y, w=THUMB_W, h=THUMB_H)
                stem = os.path.splitext(os.path.basename(sp))[0]   # "20260226_135200_bad"
                time_part = stem[9:15]  # "135200"
                label_txt = f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}" if len(time_part) == 6 else stem
                pdf.set_xy(x, y + THUMB_H + 1)
                pdf.set_font("Helvetica", "", 6)
                pdf.set_text_color(180, 180, 180)
                pdf.cell(THUMB_W, 4, _pdf_safe(label_txt), align="C")
                pdf.set_text_color(0, 0, 0)
            except Exception:
                pass

        rows_used = (len(snapshot_paths) + COLS - 1) // COLS
        pdf.ln(rows_used * (THUMB_H + GAP + 7) + 5)

    # ── Page N: Health Risk Analysis ──────────────────────────────────────
    risks = _analyse_risks(summary, rows)
    if risks:
        pdf.add_page()

        # Section header
        pdf.set_fill_color(183, 28, 28)
        pdf.rect(0, 0, 210, 18, "F")
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 4)
        pdf.cell(0, 10, _pdf_safe("Health Risk Analysis  -  Based on Today's Posture Data"), ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(6)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(
            190, 5,
            _pdf_safe(
                "The table below shows which musculoskeletal conditions you are most prone to "
                "based on the posture issues recorded today. Severity is calculated from how "
                "frequently each pattern was detected relative to your total session."
            ),
        )
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

        _render_risk_table(pdf, risks)

    pdf.output(output_path)
    return output_path


# ---------------------------------------------------------------------------
# Monthly PDF report
# ---------------------------------------------------------------------------

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def generate_monthly_pdf(year: int, month: int, output_path: Optional[str] = None) -> str:
    """
    Build a multi-page PDF monthly report for *year*/*month*.
    Returns the absolute path to the written PDF.

    Requires fpdf2:  pip install fpdf2
    """
    try:
        from fpdf import FPDF  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "fpdf2 is required for PDF reports.  "
            "Install it with:  pip install fpdf2"
        ) from exc

    month_name = _MONTH_NAMES[month - 1]
    _label     = f"Monthly Report - {month_name} {year}"
    _gen_time  = datetime.now().strftime("%d %b %Y %H:%M")

    class _PosturePDF(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(160, 160, 160)
            self.cell(
                0, 5,
                _pdf_safe(f"Posture Tracker  |  {_label}  |  Generated {_gen_time}  |  Page {self.page_no()}"),
                align="C",
            )
            self.set_text_color(0, 0, 0)

    # ── Load per-day data ──────────────────────────────────────────────────
    month_prefix = f"{year:04d}-{month:02d}-"
    all_dates    = database.get_all_dates()
    month_dates  = sorted(d for d in all_dates if d.startswith(month_prefix))

    day_summaries: list[tuple[str, dict]] = []
    all_rows: list[dict] = []
    for d in month_dates:
        try:
            s = database.get_daily_summary(d)
        except Exception:
            continue
        if s and s.get("total", 0) > 0:
            day_summaries.append((d, s))
        try:
            day_rows = database.get_records_range(d, d)
            all_rows.extend(day_rows)
        except Exception:
            pass

    # ── Monthly KPIs ───────────────────────────────────────────────────────
    total_days    = len(day_summaries)
    total_good    = sum(s.get("good", 0) for _, s in day_summaries)
    total_bad     = sum(s.get("bad", 0) for _, s in day_summaries)
    total_minutes = sum(s.get("total_minutes", 0) for _, s in day_summaries)
    avg_score     = (
        sum(s.get("good_pct", 0.0) for _, s in day_summaries) / total_days
        if total_days else 0.0
    )
    best_entry  = max(day_summaries, key=lambda x: x[1].get("good_pct", 0),   default=None)
    worst_entry = min(day_summaries, key=lambda x: x[1].get("good_pct", 100), default=None)
    raw_angles  = [s.get("avg_angle") for _, s in day_summaries if s.get("avg_angle") is not None]
    avg_angle   = sum(float(a) for a in raw_angles) / len(raw_angles) if raw_angles else None

    # ── Charts ─────────────────────────────────────────────────────────────
    day_score_pairs = [(d, s.get("good_pct", 0.0)) for d, s in day_summaries]
    monthly_bars_png = _fig_monthly_bars(day_score_pairs)
    donut_png        = _fig_donut(total_good, total_bad)

    ts_list:    list = []
    pos_list:   list = []
    angle_list: list = []
    for row in all_rows:
        try:
            ts_utc  = datetime.fromisoformat(str(row["timestamp"])).replace(tzinfo=timezone.utc)
            ts_loc  = ts_utc.astimezone()
            ts_list.append(ts_loc)
            pos_list.append(str(row["posture"]))
            a = row["fwd_angle"]
            angle_list.append(float(a) if a is not None else None)
        except Exception:
            pass

    # ── Output path ────────────────────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = str(REPORTS_DIR / f"posture_monthly_{year:04d}_{month:02d}.pdf")

    # ── Build PDF ──────────────────────────────────────────────────────────
    pdf = _PosturePDF()
    pdf.set_auto_page_break(auto=True, margin=18)

    HR, HG, HB = 48, 63, 159   # indigo header colour

    def _section_hdr(title: str) -> None:
        pdf.set_fill_color(HR, HG, HB)
        pdf.rect(0, 0, 210, 18, "F")
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 4)
        pdf.cell(0, 10, _pdf_safe(title))
        pdf.set_text_color(0, 0, 0)
        pdf.ln(22)

    def _kpi(x: float, y: float, title: str, value: str, sub: str, rgb: tuple) -> None:
        r, g, b = rgb
        # Card body
        pdf.set_fill_color(r, g, b)
        pdf.rect(x, y, 58, 28, "F")
        # Lighter top stripe
        pdf.set_fill_color(min(r + 30, 255), min(g + 30, 255), min(b + 30, 255))
        pdf.rect(x, y, 58, 6, "F")
        # Title
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(220, 220, 220)
        pdf.set_xy(x + 3, y + 1)
        pdf.cell(52, 4, _pdf_safe(title.upper()))
        # Value
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(x + 3, y + 7)
        pdf.cell(52, 11, _pdf_safe(str(value)))
        # Sub-label
        pdf.set_font("Helvetica", "", 7)
        pdf.set_xy(x + 3, y + 20)
        pdf.cell(52, 4, _pdf_safe(sub))
        pdf.set_text_color(0, 0, 0)

    # ── Page 1: Cover + KPIs + Daily Bar Chart ────────────────────────────
    pdf.add_page()

    # Cover header band
    pdf.set_fill_color(HR, HG, HB)
    pdf.rect(0, 0, 210, 36, "F")
    pdf.set_fill_color(92, 107, 192)   # lighter accent strip
    pdf.rect(0, 32, 210, 4, "F")
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 8)
    pdf.cell(0, 10, _pdf_safe("Posture Tracker - Monthly Report"), ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_xy(10, 22)
    pdf.cell(0, 6, _pdf_safe(f"{month_name} {year}  |  Generated: {_gen_time}"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(12)

    # KPI row 1
    days_total = calendar.monthrange(year, month)[1]
    score_rgb = (76, 175, 80) if avg_score >= 75 else (255, 152, 0) if avg_score >= 50 else (244, 67, 54)
    _kpi(10,  54, "Tracked Days",   str(total_days),       f"out of {days_total} days",         (HR, HG, HB))
    _kpi(73,  54, "Avg Score",      f"{avg_score:.0f}%",   "good posture across month",          score_rgb)
    _kpi(136, 54, "Total Minutes",  str(total_minutes),    "tracked this month",                 (0, 150, 136))

    # KPI row 2
    best_label  = best_entry[0][-5:]  if best_entry  else "—"
    best_sub    = f"{best_entry[1].get('good_pct', 0):.0f}% score"  if best_entry  else ""
    worst_label = worst_entry[0][-5:] if worst_entry else "—"
    worst_sub   = f"{worst_entry[1].get('good_pct', 100):.0f}% score" if worst_entry else ""
    _kpi(10,  88, "Total Alerts",   str(total_bad),        "bad-posture detections",             (183, 28, 28))
    _kpi(73,  88, "Best Day",       best_label,            best_sub,                             (76, 175, 80))
    _kpi(136, 88, "Worst Day",      worst_label,           worst_sub,                            (244, 67, 54))

    if avg_angle is not None:
        pdf.set_xy(10, 122)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 6, _pdf_safe(f"Average forward-head angle across the month: {avg_angle:.1f} deg"), ln=True)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(6)

    # Daily bar chart
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_safe("Daily Posture Scores"), ln=True)
    _tmp = io.BytesIO(monthly_bars_png)
    pdf.image(_tmp, x=10, w=190)

    # ── Page 2: Donut + angle trend ───────────────────────────────────────
    pdf.add_page()
    _section_hdr(f"Session Analysis  -  {month_name} {year}")

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_safe("Overall Good vs Bad Posture (entire month)"), ln=True)
    _tmp = io.BytesIO(donut_png)
    pdf.image(_tmp, x=65, w=80)
    pdf.ln(4)

    if ts_list:
        try:
            angle_png = _fig_angle(ts_list, angle_list)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, _pdf_safe("Forward Head Angle — All Sessions"), ln=True)
            _tmp2 = io.BytesIO(angle_png)
            pdf.image(_tmp2, x=10, w=190)
        except Exception:
            pass

    # ── Page 3: Per-day summary table ─────────────────────────────────────
    if day_summaries:
        pdf.add_page()
        _section_hdr(f"Day-by-Day Summary  -  {month_name} {year}")

        COL_WIDTHS = [32, 26, 26, 26, 30, 30, 22]
        HEADERS    = ["Date", "Score %", "Good", "Bad", "Minutes", "Avg Angle", "Rating"]
        pdf.set_fill_color(HR, HG, HB)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(255, 255, 255)
        for h, w in zip(HEADERS, COL_WIDTHS):
            pdf.cell(w, 7, _pdf_safe(h), border=0, fill=True, align="C")
        pdf.ln()
        pdf.set_text_color(0, 0, 0)

        for i, (d, s) in enumerate(day_summaries):
            row_fill = (i % 2 == 0)
            if row_fill:
                pdf.set_fill_color(235, 237, 254)
            else:
                pdf.set_fill_color(245, 246, 255)
            pct     = s.get("good_pct", 0.0)
            rating  = "Excellent" if pct >= 85 else "Good" if pct >= 70 else "Fair" if pct >= 50 else "Poor"
            avg_a   = s.get("avg_angle")
            cells   = [
                d,
                f"{pct:.0f}%",
                str(s.get("good", 0)),
                str(s.get("bad", 0)),
                str(s.get("total_minutes", 0)),
                f"{avg_a:.1f}" if avg_a is not None else "—",
                rating,
            ]
            pdf.set_font("Helvetica", "", 8)
            for cell, w in zip(cells, COL_WIDTHS):
                pdf.cell(w, 6, _pdf_safe(cell), border=0, fill=row_fill, align="C")
            pdf.ln()

    # ── Page 4: Health risk analysis ──────────────────────────────────────
    if all_rows and day_summaries:
        combined = {
            "total":         sum(s.get("total", 0) for _, s in day_summaries),
            "good":          total_good,
            "bad":           total_bad,
            "good_pct":      avg_score,
            "bad_pct":       100.0 - avg_score,
            "avg_angle":     avg_angle,
            "total_minutes": total_minutes,
        }
        risks = _analyse_risks(combined, all_rows)
        if risks:
            pdf.add_page()
            pdf.set_fill_color(183, 28, 28)
            pdf.rect(0, 0, 210, 18, "F")
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(10, 4)
            pdf.cell(0, 10, _pdf_safe(f"Health Risk Analysis  -  {month_name} {year}"))
            pdf.set_text_color(0, 0, 0)
            pdf.ln(24)

            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(
                190, 5,
                _pdf_safe(
                    "The table below aggregates musculoskeletal risk across all tracked days "
                    f"in {month_name} {year}. Severity reflects the frequency of each "
                    "bad-posture pattern relative to the month's total session data."
                ),
            )
            pdf.set_text_color(0, 0, 0)
            pdf.ln(4)

            _render_risk_table(pdf, risks)

    pdf.output(output_path)
    return output_path


# ---------------------------------------------------------------------------
# Delivery helpers
# ---------------------------------------------------------------------------


def send_email(
    pdf_path: str,
    to_addr: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    use_tls: bool = True,
) -> None:
    """Send *pdf_path* as an email attachment using SMTP (Gmail-compatible)."""
    date_str = os.path.basename(pdf_path).replace("posture_report_", "").replace(".pdf", "")
    msg = EmailMessage()
    msg["Subject"] = f"Posture Tracker — Daily Report ({date_str})"
    msg["From"]    = smtp_user
    msg["To"]      = to_addr
    msg.set_content(
        f"Hi,\n\n"
        f"Please find your posture report for {date_str} attached.\n\n"
        "Keep your chin up (but not too far forward 😄)\n\n"
        "— Posture Tracker"
    )
    with open(pdf_path, "rb") as fh:
        msg.add_attachment(
            fh.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(pdf_path),
        )
    if use_tls:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)


def open_in_explorer(pdf_path: str) -> None:
    """Open Windows Explorer with the PDF file selected."""
    subprocess.Popen(["explorer", "/select,", os.path.abspath(pdf_path)])


def share_whatsapp_web(pdf_path: str, phone: str = "") -> None:
    """
    Open WhatsApp in the browser pre-filled with a message about the report.
    The user attaches the PDF manually (WhatsApp Web does not support direct
    file attachment via URLs).  *phone* should be in E.164 format, e.g. '919876543210'.
    """
    msg = (
        f"My Posture Report — {os.path.basename(pdf_path)}\n"
        f"Generated by Posture Tracker on {datetime.now().strftime('%d %b %Y')}."
    )
    encoded = urllib.parse.quote(msg)
    if phone:
        url = f"https://wa.me/{phone.lstrip('+').strip()}?text={encoded}"
    else:
        url = "https://web.whatsapp.com/"
    webbrowser.open(url)


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------


def load_config() -> dict:
    """Load saved delivery config; return defaults if not found."""
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "email_to":       "",
            "smtp_host":      "smtp.gmail.com",
            "smtp_port":      587,
            "smtp_user":      "",
            "smtp_pass":      "",
            "use_tls":        True,
            "whatsapp_phone": "",
        }


def save_config(cfg: dict) -> None:
    """Persist delivery config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

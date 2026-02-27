"""
database.py — SQLite helpers for posture logging.

Schema:
    posture_log(id, timestamp, posture, ear_y, shoulder_y, hip_y, fwd_angle, is_owner)

All timestamps are stored as ISO-8601 UTC strings.
"""

import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posture.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS posture_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    posture     TEXT    NOT NULL,
    ear_y       REAL,
    shoulder_y  REAL,
    hip_y       REAL,
    fwd_angle   REAL,
    is_owner    INTEGER NOT NULL DEFAULT 1
);
"""


def _connect() -> sqlite3.Connection:
    """Return a connection with row-factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the posture_log table if it doesn't already exist."""
    with _connect() as conn:
        conn.execute(_CREATE_TABLE)
        conn.commit()


def insert_record(
    posture: str,
    ear_y: float,
    shoulder_y: float,
    hip_y: float,
    fwd_angle: float,
    is_owner: bool = True,
) -> None:
    """Append a single posture observation."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO posture_log (timestamp, posture, ear_y, shoulder_y, hip_y, fwd_angle, is_owner)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, posture, ear_y, shoulder_y, hip_y, fwd_angle, int(is_owner)),
        )
        conn.commit()


def get_today_records() -> list[sqlite3.Row]:
    """Return every row whose timestamp falls on today (UTC)."""
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM posture_log WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{today_prefix}%",),
        ).fetchall()
    return rows


def get_records_range(start: str, end: str) -> list[sqlite3.Row]:
    """
    Return rows between two ISO-8601 date strings (inclusive).

    Parameters
    ----------
    start : str   e.g. "2026-02-25"
    end   : str   e.g. "2026-02-25"
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM posture_log WHERE timestamp >= ? AND timestamp < date(?, '+1 day') ORDER BY timestamp",
            (start, end),
        ).fetchall()
    return rows


def get_daily_summary(date_str: str) -> dict:
    """
    Return a structured summary dict for *date_str* (e.g. '2026-02-26').

    Keys
    ----
    date, total, good, bad, good_pct, bad_pct, total_minutes,
    avg_angle, peak_bad_hour, hourly_bad (list[int] len=24)
    """
    rows = get_records_range(date_str, date_str)
    ts_list, pos_list, angle_list = [], [], []
    for row in rows:
        try:
            ts_list.append(datetime.fromisoformat(str(row["timestamp"])))
            pos_list.append(str(row["posture"]))
            a = row["fwd_angle"]
            angle_list.append(float(a) if a is not None else None)
        except Exception:
            pass

    total = len(pos_list)
    good  = pos_list.count("good")
    bad   = total - good

    hourly_bad = [0] * 24
    for ts, pos in zip(ts_list, pos_list):
        if pos == "bad":
            hourly_bad[ts.hour] += 1

    peak_bad_hour = int(hourly_bad.index(max(hourly_bad))) if total > 0 and max(hourly_bad) > 0 else None
    valid_angles  = [a for a in angle_list if a is not None]
    avg_angle     = sum(valid_angles) / len(valid_angles) if valid_angles else None

    return {
        "date":         date_str,
        "total":        total,
        "good":         good,
        "bad":          bad,
        "good_pct":     round(good / total * 100, 1) if total else 0.0,
        "bad_pct":      round(bad  / total * 100, 1) if total else 0.0,
        "total_minutes": total // 60,
        "avg_angle":    round(avg_angle, 1) if avg_angle is not None else None,
        "peak_bad_hour": peak_bad_hour,
        "hourly_bad":   hourly_bad,
    }


def get_all_dates() -> list:
    """Return sorted list of all dates (YYYY-MM-DD) that have at least one record."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT substr(timestamp, 1, 10) AS d FROM posture_log ORDER BY d"
        ).fetchall()
    return [str(r["d"]) for r in rows]


# Auto-create the table on first import.
init_db()

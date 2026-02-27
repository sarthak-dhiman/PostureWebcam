"""
camera_perms.py — Hardwired Windows camera consent manager.

Windows stores webcam access consent under two registry hives:
  HKCU  — user-level  (writable without elevation)
  HKLM  — system-wide (requires admin)

This module:
  1. Checks whether consent is already Allow.
  2. Writes HKCU keys directly (no UAC needed).
  3. Writes HKLM keys via a self-elevating UAC subprocess.
  4. Registers the running Python interpreter as an explicitly allowed app.

Entry point for the daemon: call ensure_camera_perms() at startup.
"""

import ctypes
import logging
import os
import sys
import winreg

log = logging.getLogger(__name__)

# ─── Registry paths ───────────────────────────────────────────────────────────

_HKCU_WEBCAM = (
    r"Software\Microsoft\Windows\CurrentVersion"
    r"\CapabilityAccessManager\ConsentStore\webcam"
)
_HKLM_WEBCAM = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion"
    r"\CapabilityAccessManager\ConsentStore\webcam"
)
_ALLOW = "Allow"

# Sentinel argument used when this script is re-launched elevated
_FIX_ARG = "--fix-camera-perms-elevated"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _encode_app_path(exe: str) -> str:
    """
    Encode an EXE path into the ConsentStore per-app key name format.
    Windows uses the path with backslashes replaced by '#' and the colon dropped.
    e.g. D:\\foo\\python.exe  →  D:#foo#python.exe
    """
    # Normalise separators then replace
    normed = os.path.normpath(exe)          # D:\foo\python.exe
    return normed.replace(":", "").replace("\\", "#")


def _rw_flags(write: bool = False) -> int:
    base = winreg.KEY_WOW64_64KEY
    return base | (winreg.KEY_SET_VALUE if write else winreg.KEY_READ)


def _get_value(hive, subkey: str) -> str | None:
    try:
        with winreg.OpenKey(hive, subkey, 0, _rw_flags()) as k:
            val, _ = winreg.QueryValueEx(k, "Value")
            return val
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _set_value(hive, subkey: str, value: str = _ALLOW) -> None:
    """Create key if needed and set its 'Value' string."""
    with winreg.CreateKeyEx(hive, subkey, 0, _rw_flags(write=True)) as k:
        winreg.SetValueEx(k, "Value", 0, winreg.REG_SZ, value)
        # Also stamp LastUsedTimeStop=0 so Windows keeps the entry active
        try:
            winreg.SetValueEx(k, "LastUsedTimeStop", 0, winreg.REG_QWORD, 0)
        except Exception:
            pass


# ─── Consent check ────────────────────────────────────────────────────────────

def check_camera_allowed() -> bool:
    """Return True when both HKCU and HKLM consent are Allow."""
    hkcu = _get_value(winreg.HKEY_CURRENT_USER, _HKCU_WEBCAM)
    hklm = _get_value(winreg.HKEY_LOCAL_MACHINE, _HKLM_WEBCAM)
    return hkcu == _ALLOW and hklm == _ALLOW


# ─── Apply all consent keys (must run as admin for HKLM) ─────────────────────

def _apply_all(python_exe: str) -> None:
    """
    Write every required consent key.
    Requires administrator privileges for the HKLM writes.
    """
    app_enc = _encode_app_path(python_exe)

    entries = [
        # (hive,                       subkey)
        (winreg.HKEY_CURRENT_USER,  _HKCU_WEBCAM),
        (winreg.HKEY_CURRENT_USER,  _HKCU_WEBCAM + r"\NonPackaged"),
        (winreg.HKEY_CURRENT_USER,  _HKCU_WEBCAM + r"\NonPackaged" + "\\" + app_enc),
        (winreg.HKEY_LOCAL_MACHINE, _HKLM_WEBCAM),
        (winreg.HKEY_LOCAL_MACHINE, _HKLM_WEBCAM + r"\NonPackaged"),
        (winreg.HKEY_LOCAL_MACHINE, _HKLM_WEBCAM + r"\NonPackaged" + "\\" + app_enc),
    ]

    for hive, subkey in entries:
        try:
            _set_value(hive, subkey)
            hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
            log.info("[camera_perms] Set %s\\...\\%s = Allow", hive_name, subkey.split("\\")[-1])
        except PermissionError as exc:
            log.error("[camera_perms] Permission denied on %s: %s", subkey, exc)
            raise
        except Exception as exc:
            log.warning("[camera_perms] Could not set %s: %s", subkey, exc)

    log.info("[camera_perms] All webcam consent keys written.")


# ─── HKCU-only write (no elevation) ──────────────────────────────────────────

def _apply_hkcu_only(python_exe: str) -> None:
    app_enc = _encode_app_path(python_exe)
    for subkey in [
        _HKCU_WEBCAM,
        _HKCU_WEBCAM + r"\NonPackaged",
        _HKCU_WEBCAM + r"\NonPackaged" + "\\" + app_enc,
    ]:
        try:
            _set_value(winreg.HKEY_CURRENT_USER, subkey)
        except Exception as exc:
            log.warning("[camera_perms] HKCU write failed (%s): %s", subkey, exc)


# ─── UAC self-elevation ───────────────────────────────────────────────────────

def _elevate_and_fix(python_exe: str) -> bool:
    """
    Re-launch THIS file elevated via UAC to write HKLM keys.
    Returns True if the user accepted UAC.
    """
    script = os.path.abspath(__file__)
    params = f'"{script}" {_FIX_ARG} "{python_exe}"'
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,        # hwnd
        "runas",     # verb — triggers UAC
        python_exe,  # executable
        params,      # parameters
        None,        # working dir (inherit)
        1,           # SW_NORMAL
    )
    # ShellExecute returns >32 on success
    return int(ret) > 32


# ─── Public API ───────────────────────────────────────────────────────────────

def ensure_camera_perms() -> bool:
    """
    Ensure Windows grants camera access to this Python process.

    Strategy:
      1. ALWAYS write the per-app HKCU entry for this Python exe
         (no UAC required — this is the key Windows checks per-process).
      2. If global consent is already set, return True after step 1.
      3. Otherwise write full HKCU keys.
      4. If already admin → write HKLM keys directly.
         Else → spawn an elevated copy of this script to write HKLM.
      5. Re-check and return final state.

    The per-app key is always written so that Windows recognises this
    specific Python interpreter even after a reboot or Settings reset.
    """
    python_exe = sys.executable
    app_enc = _encode_app_path(python_exe)

    # Step 1: unconditionally stamp the per-app HKCU entry (no UAC needed).
    # This is the key Windows checks at the process level — without it the
    # camera driver delivers black frames even when global consent = Allow.
    for sub in (
        _HKCU_WEBCAM,
        _HKCU_WEBCAM + r"\NonPackaged",
        _HKCU_WEBCAM + r"\NonPackaged" + "\\" + app_enc,
    ):
        try:
            _set_value(winreg.HKEY_CURRENT_USER, sub)
        except Exception as exc:
            log.warning("[camera_perms] HKCU per-app stamp failed (%s): %s", sub, exc)

    if check_camera_allowed():
        log.info("[camera_perms] Camera permissions OK (per-app key ensured).")
        return True

    log.warning("[camera_perms] Global webcam consent not fully set — attempting full fix.")

    # Full HKCU write (already done above, but ensures all keys exist)
    _apply_hkcu_only(python_exe)

    if _is_admin():
        # We already have admin rights — write everything now
        try:
            _apply_all(python_exe)
        except Exception as exc:
            log.error("[camera_perms] Admin write failed: %s", exc)
    else:
        # Spawn elevated subprocess to handle HKLM
        accepted = _elevate_and_fix(python_exe)
        if accepted:
            log.info("[camera_perms] UAC elevation accepted — HKLM keys will be set.")
        else:
            log.warning(
                "[camera_perms] UAC elevation declined — falling back to HKCU-only. "
                "Camera may still work."
            )

    ok = check_camera_allowed()
    if ok:
        log.info("[camera_perms] Camera permission verified Allow.")
    else:
        log.warning(
            "[camera_perms] Could not fully verify camera consent. "
            "If the camera fails, run tracker_daemon.py as Administrator once."
        )
    return ok


# ─── Elevated sub-process entry point ────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if _FIX_ARG in sys.argv:
        idx = sys.argv.index(_FIX_ARG)
        caller_exe = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else sys.executable
        try:
            _apply_all(caller_exe)
            print("[camera_perms] SUCCESS — all camera consent keys written.")
        except Exception as e:
            print(f"[camera_perms] FAILED: {e}")
            sys.exit(1)
    else:
        # Standalone diagnostic / fix run
        print("Admin:", _is_admin())
        print("Camera allowed before:", check_camera_allowed())
        result = ensure_camera_perms()
        print("Camera allowed after: ", result)

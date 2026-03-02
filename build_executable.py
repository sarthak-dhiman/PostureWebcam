"""
build_executable.py
===================
Step-1 of the two-step Windows packaging pipeline.

What this script does
---------------------
1.  Converts office.png → office.ico  (required by the .spec for exe icons)
2.  Verifies PyInstaller is installed in the active venv
3.  Runs PyInstaller with PostureApp.spec  (--onedir, --windowed)
4.  Post-processes the dist/PostureApp/ folder:
      • Creates empty writable subdirectories (data/reports/, data/snapshots/, …)
      • Removes user-specific files accidentally bundled (auth_cache, jwt_cache)
      • Writes a build_info.json with timestamp and git hash (if available)
5.  Prints a summary with next steps for Inno Setup

Usage
-----
    # From the project root with the venv activated:
    python build_executable.py

    # Skip clean to re-use an existing build directory:
    python build_executable.py --no-clean

    # Enable verbose PyInstaller output:
    python build_executable.py --verbose
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist" / "PostureApp"
SPEC = ROOT / "PostureApp.spec"
ICO  = ROOT / "office.ico"
PNG  = ROOT / "office.png"

# ── Sensitive / user files that must NEVER be shipped ───────────────────────
_STRIP_FILES = [
    "data/auth_cache.json",
    "data/jwt_cache.json",
    "data/tracker_daemon.pid",
    "live_stats.json",
    "live_frame.jpg",
]

# ── Empty directories to create inside the dist (ensure writable at runtime) ─
_ENSURE_DIRS = [
    "data",
    "data/reports",
    "data/snapshots",
    "data/segregated",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _step(msg: str):
    print(f"\n\033[1;36m» {msg}\033[0m")


def _ok(msg: str):
    print(f"  \033[32m✔  {msg}\033[0m")


def _warn(msg: str):
    print(f"  \033[33m⚠  {msg}\033[0m")


def _fail(msg: str):
    print(f"  \033[31m✘  {msg}\033[0m")
    sys.exit(1)


def _convert_icon():
    """Convert office.png to office.ico (multi-size) using Pillow."""
    _step("Converting office.png → office.ico")
    if not PNG.exists():
        _fail(f"office.png not found at {PNG}")
    try:
        from PIL import Image
    except ImportError:
        _fail("Pillow is not installed. Run:  pip install Pillow")

    img = Image.open(PNG).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons = [img.resize(s, Image.LANCZOS) for s in sizes]
    icons[0].save(
        ICO,
        format="ICO",
        sizes=sizes,
        append_images=icons[1:],
    )
    _ok(f"Saved {ICO}")


def _check_pyinstaller():
    """Ensure PyInstaller >= 5 is importable in the current interpreter."""
    _step("Checking PyInstaller")
    try:
        import PyInstaller as _pi
        version = tuple(int(x) for x in _pi.__version__.split(".")[:2])
        if version < (5, 0):
            _fail(f"PyInstaller >= 5.0 required, found {_pi.__version__}")
        _ok(f"PyInstaller {_pi.__version__} found")
    except ImportError:
        _fail("PyInstaller not found. Run:  pip install pyinstaller")


def _clean():
    """Remove previous build/ and dist/ artefacts."""
    _step("Cleaning previous build artefacts")
    for d in (ROOT / "build", ROOT / "dist"):
        if d.exists():
            shutil.rmtree(d)
            _ok(f"Removed {d}")
    # Remove stale spec-generated __pycache__
    for p in ROOT.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    _ok("__pycache__ cleared")


def _run_pyinstaller(verbose: bool):
    """Run PyInstaller with the spec file."""
    _step("Running PyInstaller (this takes a few minutes…)")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        str(SPEC),
    ]
    if verbose:
        cmd.append("--log-level=INFO")
    else:
        cmd.append("--log-level=WARN")

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        _fail("PyInstaller exited with errors. See output above.")
    _ok("PyInstaller finished successfully")


def _post_process():
    """Clean sensitive files and ensure required dirs exist in the dist."""
    _step("Post-processing dist/PostureApp/")

    if not DIST.exists():
        _fail(f"dist directory not found at {DIST}")

    # Remove user/session files that must not be shipped
    for rel in _STRIP_FILES:
        target = DIST / rel
        if target.exists():
            target.unlink()
            _warn(f"Removed sensitive file: {target.relative_to(DIST)}")

    # Ensure writable subdirectories exist (empty — created at install time)
    for rel in _ENSURE_DIRS:
        d = DIST / rel
        d.mkdir(parents=True, exist_ok=True)
    _ok("Runtime directories created")

    # Write a build_info.json for diagnostics / update checks
    build_info = {
        "build_time_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
    }
    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        build_info["git_commit"] = git_hash
    except Exception:
        pass

    info_path = DIST / "build_info.json"
    info_path.write_text(json.dumps(build_info, indent=2), encoding="utf-8")
    _ok(f"Wrote {info_path.name}")


def _print_summary():
    """Print next-step instructions."""
    _step("Build complete!")
    print()
    print("  Output directory:")
    print(f"    {DIST}")
    print()
    print("  ── Next step: Inno Setup ─────────────────────────────────────")
    print("  1. Install Inno Setup 6  (https://jrsoftware.org/isinfo.php)")
    print("  2. Open webcam_guardian_setup.iss in the Inno Setup IDE,")
    print("     or compile from the command line:")
    print()
    iscc = r'  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" webcam_guardian_setup.iss'
    print(iscc)
    print()
    print("  The installer will be written to  dist/WebcamGuardianSetup.exe")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build PostureApp distributable")
    parser.add_argument("--no-clean",  action="store_true", help="Skip cleaning previous build")
    parser.add_argument("--verbose",   action="store_true", help="Verbose PyInstaller output")
    parser.add_argument("--skip-icon", action="store_true", help="Skip icon conversion (use existing .ico)")
    args = parser.parse_args()

    print("\n\033[1;35m╔══════════════════════════════════════════╗")
    print("║   Posture App — Windows Build Pipeline   ║")
    print("╚══════════════════════════════════════════╝\033[0m")

    if not args.skip_icon:
        _convert_icon()
    else:
        if not ICO.exists():
            _fail("--skip-icon used but office.ico not found. Run without --skip-icon first.")
        _ok("Skipping icon conversion (office.ico already present)")

    _check_pyinstaller()

    if not args.no_clean:
        _clean()

    _run_pyinstaller(args.verbose)
    _post_process()
    _print_summary()


if __name__ == "__main__":
    main()

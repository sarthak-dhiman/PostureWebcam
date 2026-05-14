# PostureCam.spec
# ============================================================
# PyInstaller spec for Posture Webcam Analyzer
#
# Produces TWO executables inside the same dist/PostureCam/ directory:
#   PostureCam.exe       - main GUI  (windowed, no console)
#   tracker_daemon.exe   - posture inference daemon  (windowed, no console)
#
# Build:  pyinstaller PostureCam.spec
# ============================================================

import sys, os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

# ── Filters to exclude heavy unnecessary submodules ──────────────────────────
def mediapipe_filter(name):
    # Exclude GenAI/LLM-related submodules which require Torch/JAX/SentencePiece
    return "mediapipe.tasks.python.genai" not in name

def onnxruntime_filter(name):
    # Exclude quantization and backend utilities which require the 'onnx' package
    return "onnxruntime.quantization" not in name and "onnxruntime.backend" not in name


# ── Root of the source tree ──────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(SPEC))   # noqa: F821 (SPEC injected by PyInstaller)

# ── Helper: relative path inside ROOT ────────────────────────────────────────
def src(*parts):
    return os.path.join(ROOT, *parts)

# ── Helper: filter out missing files from datas list ──────────────────────────
def filter_datas(datas):
    valid = []
    for s, d in datas:
        if os.path.exists(s):
            valid.append((s, d))
        else:
            print(f"  [SPEC] Skipping missing data file: {s}")
    return valid

app_datas = filter_datas([
    # App icons
    (src("office.png"),                          "."),
    (src("office.ico"),                          "."),
    # MediaPipe task models
    (src("pose_landmarker_lite.task"),            "."),
    (src("pose_landmarker_full.task"),            "."),
    # SVG / PNG icon assets
    (src("icons"),                               "icons"),
    # Default config files (no auth/session files)
    (src("data", "app_config.json"),             "data"),
    (src("data", "distance_calibration.json"),   "data"),
])

# Package-level data files auto-collected from installed packages
app_datas += [
    *collect_data_files("mediapipe",             subdir=None),
    *collect_data_files("cv2",                   subdir=None),
    *collect_data_files("face_recognition_models"),
    *collect_data_files("onnxruntime",           subdir=None),
]

# ============================================================
# HIDDEN IMPORTS
# ============================================================
hidden = [
    # ── PyQt6 ─────────────────────────────────────────────
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
    "PyQt6.sip",
    # ── MediaPipe ─────────────────────────────────────────
    "mediapipe",
    "mediapipe.tasks",
    "mediapipe.tasks.python",
    "mediapipe.tasks.python.vision",
    "mediapipe.tasks.python.core",
    "mediapipe.tasks.python.core.base_options",
    # *collect_submodules("mediapipe") -- Removed: collect_all() handles this with filters.

    # ── OpenCV ────────────────────────────────────────────
    "cv2",
    # ── ONNX Runtime ──────────────────────────────────────
    "onnxruntime",
    "onnxruntime.capi",
    "onnxruntime.capi.onnxruntime_pybind11_state",
    # ── Face recognition / dlib ───────────────────────────
    "face_recognition",
    "face_recognition_models",
    "dlib",
    # ── Notification / tray ───────────────────────────────
    "plyer",
    "plyer.platforms.win.notification",
    "pystray",
    "pystray._win32",
    # ── PIL ───────────────────────────────────────────────
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    # ── Misc runtime-imported modules ─────────────────────
    # keyring is not installed in this venv — omitted.
    "requests",
    "urllib.request",
    "urllib.error",
    "matplotlib",
    "plotly",
    "flask",
    "sqlalchemy",
    "database",
    "camera_perms",
    "unittest",  # required by pyparsing -> matplotlib -> mediapipe
    "unittest.mock",
]

# ============================================================
# COLLECT-ALL packages (carry lots of compiled extensions)
# ============================================================
# collect_all returns (datas, binaries, hiddenimports)
_mp_d, _mp_b, _mp_h   = collect_all("mediapipe", filter_submodules=mediapipe_filter)
_cv_d, _cv_b, _cv_h   = collect_all("cv2")
_or_d, _or_b, _or_h   = collect_all("onnxruntime", filter_submodules=onnxruntime_filter)
_fr_d, _fr_b, _fr_h   = collect_all("face_recognition_models")


extra_datas    = _mp_d  + _cv_d  + _or_d  + _fr_d
# Add common MKL / OpenMP runtime DLLs from typical Python/Conda locations
# (these are often required by onnxruntime on Windows and can be missing
# on target machines). We prefer DLLs found in the active Python/Conda
# `Library/bin` directories.
mkl_bins = []
possible_bin_dirs = [
    os.path.join(sys.exec_prefix, 'Library', 'bin'),
    os.path.join(os.environ.get('CONDA_PREFIX', ''), 'Library', 'bin'),
    os.path.join(os.path.expanduser('~'), 'miniconda3', 'Library', 'bin'),
]
for bdir in possible_bin_dirs:
    if bdir and os.path.isdir(bdir):
        for fname in ('mkl_rt.dll', 'libmkl_intel_lp64.dll', 'libiomp5md.dll'):
            p = os.path.join(bdir, fname)
            if os.path.exists(p):
                # Analysis(binaries=...) expects (source_full_path, dest_dir_relative)
                mkl_bins.append((p, '.'))

# Also attempt to include common MSVC CRTs which can be required by
# native extensions when the Visual C++ Redistributable is not present
# on target machines. We search a few likely locations (Python DLLs,
# Library/bin, and onnxruntime package folder collected above).
msvc_bins = []
msvc_names = ('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll', 'ucrtbase.dll')
possible_msvc_dirs = list(possible_bin_dirs) + [
    os.path.join(sys.exec_prefix, 'DLLs'),
    os.path.join(sys.base_prefix, 'DLLs'),
]
# Include any copies that were collected by collect_all for onnxruntime
for tup in _or_b:
    try:
        # Handle both (path, dest) 2-tuples and (name, path, type) 3-tuples.
        # IMPORTANT: do NOT use 'src' as a variable name here — it shadows the
        # src() helper function defined above and breaks all later src() calls.
        _dll_src = tup[1] if len(tup) == 3 else tup[0]
        if os.path.basename(_dll_src).lower() in msvc_names + ('onnxruntime.dll', 'onnxruntime_providers_shared.dll'):
            msvc_bins.append((_dll_src, '.'))
    except Exception:
        pass

for bdir in possible_msvc_dirs:
    if bdir and os.path.isdir(bdir):
        for fname in msvc_names:
            p = os.path.join(bdir, fname)
            if os.path.exists(p):
                msvc_bins.append((p, '.'))

# Deduplicate by target name (keep first found)
seen = set()
def unique_bins(bins):
    out = []
    for entry in bins:
        if entry[0] in seen:
            continue
        seen.add(entry[0])
        out.append(entry)
    return out

# ── Ensure all collected binaries/datas are 2-tuples (source, dest) ───────────
# Some PyInstaller versions or hooks might return 3-tuples (name, path, type).
# Analysis() strictly requires 2-tuples.
def fix_tuples(items):
    out = []
    for item in items:
        if len(item) >= 2:
            # If it's a 3-tuple (name, path, type), we want (path, dest_dir)
            # but usually it's (source, dest). If it's (name, path, type) 
            # we'll assume the 2nd is the source and we'll put it in root.
            if len(item) == 3 and isinstance(item[2], str) and item[2] == 'BINARY':
                 out.append((item[1], '.'))
            else:
                 out.append((item[0], item[1]))
    return out

extra_binaries = fix_tuples(_mp_b + _cv_b + _or_b + _fr_b + unique_bins(mkl_bins + msvc_bins))
extra_datas    = fix_tuples(_mp_d + _cv_d + _or_d + _fr_d)
extra_hidden   = _mp_h + _cv_h + _or_h + _fr_h + hidden

# ============================================================
# RUNTIME HOOK
# ============================================================
runtime_hooks = [src("rthook_paths.py")]

# ============================================================
# ANALYSIS — Main GUI (main.py)
# ============================================================
a_main = Analysis(
    [src("main.py")],
    pathex=[ROOT],
    binaries=extra_binaries,
    datas=app_datas + extra_datas,
    hiddenimports=extra_hidden,
    hookspath=[],
    runtime_hooks=runtime_hooks,
    excludes=[
        "tkinter", "_tkinter",
        "test",
        "IPython", "jupyter",
        "scipy", "sklearn",
        # Explicitly exclude missing heavy deps to suppress collection warnings
        "torch", "jax", "sentencepiece", "onnx",
        "mediapipe.tasks.python.genai",
        "onnxruntime.quantization",
        "pyqtgraph", "streamlit",
    ],


    noarchive=False,
)

pyz_main = PYZ(a_main.pure, a_main.zipped_data)  # noqa: F821

exe_main = EXE(                                    # noqa: F821
    pyz_main,
    a_main.scripts,
    [],
    exclude_binaries=True,           # binaries go into COLLECT (--onedir)
    name="PostureCam",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                   # --windowed: no black terminal
    icon=src("office.ico"),          # generated by build_executable.py
)

# ============================================================
# ANALYSIS — Tracker Daemon (tracker_daemon.py)
# ============================================================
a_daemon = Analysis(
    [src("tracker_daemon.py")],
    pathex=[ROOT],
    binaries=extra_binaries,
    datas=app_datas + extra_datas,
    hiddenimports=extra_hidden,
    hookspath=[],
    runtime_hooks=runtime_hooks,
    excludes=[
        "tkinter", "_tkinter",
        "test",
        "IPython", "jupyter",
        "scipy", "sklearn",
        # Explicitly exclude missing heavy deps to suppress collection warnings
        "torch", "jax", "sentencepiece", "onnx",
        "mediapipe.tasks.python.genai",
        "onnxruntime.quantization",
        "pyqtgraph", "streamlit",
    ],


    noarchive=False,
)

pyz_daemon = PYZ(a_daemon.pure, a_daemon.zipped_data)  # noqa: F821

exe_daemon = EXE(                                       # noqa: F821
    pyz_daemon,
    a_daemon.scripts,
    [],
    exclude_binaries=True,
    name="tracker_daemon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                   # no console window for daemon either
    icon=src("office.ico"),
)

# ============================================================
# COLLECT — merge both EXEs into one dist/PostureApp/ folder
# ============================================================
coll = COLLECT(                                         # noqa: F821
    exe_main,
    a_main.binaries,
    a_main.zipfiles,
    a_main.datas,

    exe_daemon,
    a_daemon.binaries,
    a_daemon.zipfiles,
    a_daemon.datas,

    strip=False,
    upx=False,
    upx_exclude=[
        # UPX can corrupt these; skip them
        "vcruntime140.dll",
        "msvcp140.dll",
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Widgets.dll",
        "python310.dll",
        "onnxruntime.dll",
        "onnxruntime_providers_shared.dll",
    ],
    name="PostureCam",               # → dist/PostureCam/
)

# ============================================================
# BUNDLE (macOS)
# ============================================================
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='PostureCam.app',
        icon=src("office.icns") if os.path.exists(src("office.icns")) else None,
        bundle_identifier='com.sarthak-dhiman.posturecam',
        info_plist={
            'NSCameraUsageDescription': 'PostureCam needs access to your camera to analyze your posture and provide ergonomic feedback.',
            'LSMinimumSystemVersion': '10.13.0',
            'NSHighResolutionCapable': True,
        },
    )


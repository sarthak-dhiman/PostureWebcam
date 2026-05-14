"""
rthook_paths.py — PyInstaller runtime hook.

Loaded automatically by every frozen executable produced from this spec.
Patches os.path / sys values so that all __file__-relative path constants
in the app still resolve to the correct location at runtime inside the
deployed dist/ folder.
"""
import os
import sys
import ctypes

# sys._MEIPASS is set by PyInstaller to the temp extraction folder for
# --onefile, or to the bundled _internal directory for modern --onedir builds.
_EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
_MEIPASS = getattr(sys, "_MEIPASS", None)
_BASE = _MEIPASS or _EXE_DIR

# Ensure the base directory is first on sys.path so that all top-level
# modules (core, views, widgets, …) import correctly from the bundle.
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

# Add bundled native-library folders to Windows DLL search path so that native
# extensions (like ONNX Runtime's pybind11 module) can find their DLL
# dependencies at runtime.
# This is critical on systems where the system \System32 copies are missing
# or incompatible.
_candidate_dll_dirs = [
    _BASE,
    os.path.join(_BASE, "_internal"),
    os.path.join(_BASE, "onnxruntime", "capi"),
    os.path.join(_BASE, "_internal", "onnxruntime", "capi"),
    os.path.join(_EXE_DIR, "_internal"),
    os.path.join(_EXE_DIR, "_internal", "onnxruntime", "capi"),
]

_dll_dirs = []
for _dir in _candidate_dll_dirs:
    if os.path.isdir(_dir) and _dir not in _dll_dirs:
        _dll_dirs.append(_dir)

_DLL_DIR_HANDLES = []
for _dll_dir in _dll_dirs:
    try:
        # Python 3.8+: add to DLL search path (most reliable)
        _DLL_DIR_HANDLES.append(os.add_dll_directory(_dll_dir))
    except (AttributeError, OSError):
        # Fallback for older Python or if add_dll_directory fails:
        # prepend to PATH so LoadLibrary searches here first
        pass

if _dll_dirs:
    os.environ["PATH"] = os.pathsep.join(_dll_dirs) + os.pathsep + os.environ.get("PATH", "")

_PRELOADED_DLL_HANDLES = []
for _dll_dir in _dll_dirs:
    for _dll_name in ("onnxruntime_providers_shared.dll", "onnxruntime.dll"):
        _dll_path = os.path.join(_dll_dir, _dll_name)
        if os.path.isfile(_dll_path):
            try:
                _PRELOADED_DLL_HANDLES.append(ctypes.WinDLL(_dll_path))
            except OSError:
                pass

# Ensure the data/ subdirectory exists in the writable app-data location.
# For a per-user install the writable root equals the exe directory;
# nothing extra is needed here.
_data_dir = os.path.join(_BASE, "data")
try:
    os.makedirs(_data_dir, exist_ok=True)
except Exception:
    pass

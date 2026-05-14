#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SCRIPT="$ROOT_DIR/build_executable.py"
DIST_DIR="$ROOT_DIR/dist/PostureCam"
DMG_PATH="$ROOT_DIR/dist/PostureCamSetup.dmg"

echo "==> Validating prerequisites"
if [ ! -f "$BUILD_SCRIPT" ]; then
    echo "Build script not found: $BUILD_SCRIPT"
    exit 1
fi

PYTHON_EXE="python3"
if [ -f "$ROOT_DIR/venv310/bin/python" ]; then
    PYTHON_EXE="$ROOT_DIR/venv310/bin/python"
elif ! command -v $PYTHON_EXE &> /dev/null; then
    echo "python3 is not on PATH and venv python was not found."
    exit 1
fi

echo "Python: $PYTHON_EXE"

echo "==> Building PostureCam dist with production endpoints"
cd "$ROOT_DIR"
$PYTHON_EXE "$BUILD_SCRIPT"

if [ ! -d "$DIST_DIR" ]; then
    echo "Built app directory not found: $DIST_DIR"
    exit 1
fi
echo "Built app directory: $DIST_DIR"

echo "==> Compiling installer for macOS (.dmg)"
if command -v hdiutil &> /dev/null; then
    # Create DMG
    rm -f "$DMG_PATH"
    # We package the PostureCam.app created by BUNDLE directive
    APP_DIR="$ROOT_DIR/dist/PostureCam.app"
    if [ -d "$APP_DIR" ]; then
        hdiutil create -volname "PostureCam" -srcfolder "$APP_DIR" -ov -format UDZO "$DMG_PATH"
        echo "Release installer ready: $DMG_PATH"
    else
        echo "PostureCam.app not found. Falling back to packaging the dist directory."
        hdiutil create -volname "PostureCam" -srcfolder "$DIST_DIR" -ov -format UDZO "$DMG_PATH"
        echo "Release installer ready: $DMG_PATH"
    fi
else
    echo "hdiutil not found. DMG creation is only supported on macOS."
    echo "App build is ready at: $DIST_DIR"
fi

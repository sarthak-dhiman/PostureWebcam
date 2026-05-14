#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SCRIPT="$ROOT_DIR/build_executable.py"
DIST_DIR="$ROOT_DIR/dist/PostureCam"
TAR_PATH="$ROOT_DIR/dist/PostureCam-Linux.tar.gz"

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

echo "==> Compiling installer for Linux (.tar.gz)"
cd "$ROOT_DIR/dist"
tar -czvf "PostureCam-Linux.tar.gz" "PostureCam"
echo "Release installer ready: $TAR_PATH"

# Try to create a makeself installer if makeself is available
if command -v makeself &> /dev/null; then
    RUN_PATH="$ROOT_DIR/dist/PostureCamSetup.run"
    echo "==> Compiling makeself installer (.run)"
    makeself "$DIST_DIR" "$RUN_PATH" "PostureCam" ./PostureCam
    echo "Release installer ready: $RUN_PATH"
else
    echo "makeself not found. Skipping .run installer creation."
    echo "You can install makeself to create a self-extracting installer."
fi

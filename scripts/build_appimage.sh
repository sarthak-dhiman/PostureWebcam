#!/usr/bin/env bash
set -euo pipefail

# Simple helper to pack dist/PostureApp into an AppImage
# Usage: ./scripts/build_appimage.sh

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [ ! -d dist/PostureApp ]; then
  echo "dist/PostureApp not found. Run build_executable.py first." >&2
  exit 1
fi

mkdir -p AppDir/usr/bin
cp -r dist/PostureApp/* AppDir/usr/bin/

cat > AppDir/PostureApp.desktop <<'EOF'
[Desktop Entry]
Name=PostureApp
Exec=PostureApp/PostureApp
Icon=office
Type=Application
Categories=Utility;
EOF

# Download appimagetool if not present
if [ ! -f appimagetool.AppImage ]; then
  echo "Downloading appimagetool..."
  wget -q https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage -O appimagetool.AppImage
  chmod +x appimagetool.AppImage
fi

./appimagetool.AppImage AppDir || true
echo "AppImage build finished (check current directory)"

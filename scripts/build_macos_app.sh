#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="VespeR"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
DMG_STAGING_DIR="$BUILD_DIR/dmg"
APP_BUNDLE_PATH="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/$APP_NAME-macOS.dmg"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This build script only supports macOS."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to build the frontend."
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import importlib.util
import sys

required = ["PyInstaller", "webview"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print("Missing Python packages:", ", ".join(missing))
    print("Install them with: pip install -e '.[desktop-build]'")
    sys.exit(1)
PY

echo "Building frontend bundle..."
npm -C frontend run build

echo "Building macOS app bundle..."
rm -rf "$APP_BUNDLE_PATH" "$DMG_PATH" "$DMG_STAGING_DIR"
env -i \
  PATH="$PATH" \
  HOME="$HOME" \
  USER="${USER:-}" \
  SHELL="${SHELL:-/bin/zsh}" \
  LANG="${LANG:-en_US.UTF-8}" \
  TERM="${TERM:-xterm-256color}" \
  PYTHONNOUSERSITE=1 \
  PYTHONPATH= \
  "$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "ai.ranausman.vesper" \
  --collect-data agentling \
  --hidden-import webview.platforms.cocoa \
  --exclude-module PyQt5 \
  --exclude-module PyQt6 \
  --exclude-module PySide2 \
  --exclude-module PySide6 \
  --exclude-module qtpy \
  --exclude-module tkinter \
  --exclude-module matplotlib \
  --exclude-module IPython \
  --exclude-module pytest \
  --exclude-module sphinx \
  --add-data "frontend/dist:frontend/dist" \
  agentling/desktop_app.py

if [[ ! -d "$APP_BUNDLE_PATH" ]]; then
  echo "Expected app bundle not found at $APP_BUNDLE_PATH"
  exit 1
fi

mkdir -p "$DMG_STAGING_DIR"
cp -R "$APP_BUNDLE_PATH" "$DMG_STAGING_DIR/"
ln -s /Applications "$DMG_STAGING_DIR/Applications"

echo "Creating DMG..."
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DMG_STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

rm -rf "$DMG_STAGING_DIR"

echo
echo "Build complete:"
echo "  App: $APP_BUNDLE_PATH"
echo "  DMG: $DMG_PATH"

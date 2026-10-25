#!/bin/sh
# Renders the link previews (Russian and English) and the touch icon for site/ with headless Chrome.
set -e
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
render() { "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --virtual-time-budget=3000 --window-size="$2" --screenshot="$3" "file://$PWD/$1" >/dev/null 2>&1; }
render og-image.html 1200,630 ../../site/og.png
render og-image.html#en 1200,630 ../../site/og-en.png
render apple-touch-icon.html 180,180 ../../site/apple-touch-icon.png

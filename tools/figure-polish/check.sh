#!/usr/bin/env bash
set -euo pipefail
polish_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export FONTCONFIG_FILE="$polish_root/config/diagram-governance/fonts.conf"
export PLAYWRIGHT_BROWSERS_PATH="$polish_root/.diagram-governance/browsers"
polish_browser_cache="$HOME/.cache/auv-diagram-governance/browsers"
if [[ -x "$polish_browser_cache/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell" ]]; then
  export PLAYWRIGHT_BROWSERS_PATH="$polish_browser_cache"
fi
export PYTHONPATH="$polish_root/.diagram-governance/pydeps${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$polish_root/tools/figure-polish/check_drawio.py" "$@"

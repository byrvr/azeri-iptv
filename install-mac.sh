#!/bin/bash
# Install (or update) the daily auto-update job on this Mac with launchd.
#
#   ./install-mac.sh              # install / reinstall; runs daily at 06:00
#   HOUR=4 ./install-mac.sh       # different hour
#   ./install-mac.sh --uninstall  # remove the job (keeps the clone)
#
# The job runs from its own clone in ~/Library/Application Support/azeri-iptv,
# so don't edit files there: every run resets it to origin/main. If the Mac is
# asleep at the scheduled time, launchd runs the job when it wakes.
set -euo pipefail

LABEL=com.byrvr.azeri-iptv
DIR="$HOME/Library/Application Support/azeri-iptv"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/azeri-iptv.log"
REPO=https://github.com/byrvr/azeri-iptv.git
HOUR=${HOUR:-6}
DOMAIN="gui/$(id -u)"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $LABEL (clone left in $DIR)"
  exit 0
fi

PY=$(command -v python3)
GIT=$(command -v git)
GH=$(command -v gh || true)

if [[ -d "$DIR/.git" ]]; then
  git -C "$DIR" fetch -q origin
  git -C "$DIR" reset -q --hard origin/main
else
  mkdir -p "$(dirname "$DIR")"
  git clone -q "$REPO" "$DIR"
fi

PATH_DIRS="$(dirname "$PY"):$(dirname "$GIT")"
[[ -n "$GH" ]] && PATH_DIRS="$PATH_DIRS:$(dirname "$GH")"

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$DIR/autoupdate.py</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$PATH_DIRS:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"

echo "installed $LABEL: daily at $(printf '%02d' "$HOUR"):00, or on wake if the Mac was asleep"
echo "clone: $DIR"
echo "log:   $LOG"
echo "run it now: launchctl kickstart $DOMAIN/$LABEL"

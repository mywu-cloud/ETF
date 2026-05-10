#!/usr/bin/env bash
# 每日 21:00 由 launchd 呼叫：抓取 00981A + 00992A 持股並更新 HTML
set -euo pipefail

PYTHON=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3
DIR="/Users/mykerwu/Library/Mobile Documents/com~apple~CloudDocs/ETF_00981A"
LOG="$DIR/logs/daily.log"

mkdir -p "$DIR/logs"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"

echo "[00981A] fetch..." >> "$LOG"
"$PYTHON" "$DIR/tracker.py"     fetch >> "$LOG" 2>&1
"$PYTHON" "$DIR/make_html.py"         >> "$LOG" 2>&1

echo "[00992A] fetch..." >> "$LOG"
"$PYTHON" "$DIR/tracker_00992A.py"   fetch >> "$LOG" 2>&1
"$PYTHON" "$DIR/make_html_00992A.py"       >> "$LOG" 2>&1

echo "=== done ===" >> "$LOG"

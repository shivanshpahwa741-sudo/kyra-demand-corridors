#!/bin/bash
# Daily refresh: scrape → rebuild viz → commit → push to GitHub Pages.
# Runs via launchd (see com.kyra.corridors.plist).
set -e
cd "$(dirname "$0")"

export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"
LOG="refresh.log"
exec >> "$LOG" 2>&1
echo
echo "===== $(date) ====="

# 1. Scrape
echo "[scrape]"
python3.12 scrape.py
cp data/bookings.json pipeline/bookings.json

# 2. Rebuild viz
echo "[pipeline]"
cd pipeline
python3.12 locality_pipeline.py
python3.12 build_map.py
cd ..

# 3. Inline + copy to repo root
python3.12 inline_viz.py

# 4. Commit + push
if git diff --quiet index.html; then
  echo "[git] no changes"
else
  git add index.html
  git commit -m "Daily refresh $(date +%Y-%m-%d)"
  git push origin main
  echo "[git] pushed"
fi

echo "done"

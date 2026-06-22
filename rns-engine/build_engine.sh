#!/usr/bin/env bash
# Build the rns-engine sidecar into a single executable (like sing-box.exe).
# Output: dist/rns-engine(.exe). Then bundle it as a Tauri resource.
set -euo pipefail
cd "$(dirname "$0")"

python -m pip install -r requirements.txt
python -m pip install pyinstaller

pyinstaller --onefile --name rns-engine \
  --collect-all RNS \
  --collect-all LXMF \
  rns_engine.py

echo
echo "Built: $(ls -1 dist/rns-engine* 2>/dev/null)"
echo "Next: copy dist/rns-engine* into tauri-app/src-tauri/ and set"
echo "      \"bundle\": { \"resources\": [\"rns-engine*\"] } in tauri.conf.json"

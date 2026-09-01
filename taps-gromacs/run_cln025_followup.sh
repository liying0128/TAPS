#!/usr/bin/env bash
# Wait for unfolded CLN025 100 ns cMD, then run TAPS / LAST / Least-counts in order.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
OUT="$ROOT/analysis/cln025_unfolded"
mkdir -p "$OUT"
LOG="$OUT/followup.log"

exec > >(tee -a "$LOG") 2>&1

echo "============================================================"
echo "[$(date '+%F %T')] followup start  pid=$$"
echo "waiting for: $ROOT/systems/chignolin_cln025/water_unfolded/runs/md_100ns"
echo "============================================================"

PROD_LOG="$ROOT/systems/chignolin_cln025/water_unfolded/runs/md_100ns.log"
PROD_GRO="$ROOT/systems/chignolin_cln025/water_unfolded/runs/md_100ns.gro"
PROD_XTC="$ROOT/systems/chignolin_cln025/water_unfolded/runs/md_100ns.xtc"

while true; do
  if [[ -f "$PROD_LOG" && -f "$PROD_GRO" && -f "$PROD_XTC" ]] \
     && grep -q "Finished mdrun" "$PROD_LOG"; then
    if ! pgrep -f "mdrun .*runs/md_100ns" >/dev/null 2>&1; then
      break
    fi
    echo "[$(date '+%F %T')] log says finished, mdrun still exiting — wait"
  else
    last=""
    if [[ -f "$PROD_LOG" ]]; then
      last=$(awk '/^[[:space:]]+[0-9]+[[:space:]]+[0-9.]+[[:space:]]*$/{t=$2} END{if(t!="") printf "%.1f ns", t/1000}' "$PROD_LOG")
    fi
    echo "[$(date '+%F %T')] waiting for 100 ns cMD  (${last:-no time yet})"
  fi
  sleep 30
done

echo "[$(date '+%F %T')] 100 ns cMD finished — 15s settle"
sleep 15

echo "[$(date '+%F %T')] STAGE 13  TAPS → LAST → Least-counts"
python3 "$ROOT/stage13_cln025_discover.py"
rc=$?
echo "[$(date '+%F %T')] stage13 exit=$rc"
if [[ $rc -ne 0 ]]; then
  echo "STAGE 13 failed. Re-run: python3 $ROOT/stage13_cln025_discover.py"
  exit $rc
fi
echo "[$(date '+%F %T')] followup done  report: $OUT/discover_last/report.txt"
exit 0

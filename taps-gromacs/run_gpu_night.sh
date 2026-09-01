#!/usr/bin/env bash
# GPU night queue AFTER the running Hybrid-08 campaigns.
# Leaves CPU cores 8-31 for the CPU night queue (--nt 8 here).
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
OUT="$ROOT/analysis/hybrid"
mkdir -p "$OUT"
LOG="$OUT/gpu_night.log"
export PYTHONUNBUFFERED=1
NT=8

exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] GPU night waiter  pid=$$"
echo "waiting for hybrid08_run_campaign.py to finish"
echo "============================================================"

while pgrep -f '[p]ython3 hybrid08_run_campaign.py' >/dev/null 2>&1; do
  echo "[$(date '+%F %T')] hybrid08 still running"
  sleep 60
done

echo "[$(date '+%F %T')] hybrid08 done — start GPU follow-on"

run() {
  echo
  echo "----- [$(date '+%F %T')] $* -----"
  if ! "$@"; then
    echo "[$(date '+%F %T')] FAILED (continue): $*"
  fi
}

# §8 coverage-saturation LAST→TAPS
run python3 hybrid08_run_campaign.py --gpu --nt "$NT" --schedules hybrid_cov

# replicate of the offline-best schedule
run python3 hybrid08_run_campaign.py --gpu --nt "$NT" --schedules hybrid3_75 --tag-suffix _s1 --seed 1
run python3 hybrid08_run_campaign.py --gpu --nt "$NT" --schedules hybrid2_50 --tag-suffix _s1 --seed 1
run python3 hybrid08_run_campaign.py --gpu --nt "$NT" --schedules hybrid1_25 --tag-suffix _s1 --seed 1
run python3 hybrid08_run_campaign.py --gpu --nt "$NT" --schedules hybrid3_75 --tag-suffix _s2 --seed 2

# longer unfolded cMD baseline (productive-exploration matched budget)
run python3 run_md.py --system cln025_unfolded --length 400 --nt "$NT"
run python3 run_md.py --system cln025_unfolded --length 500 --nt "$NT"

# native CLN025 extra production
run python3 run_md.py --system cln025_water --length 200 --nt "$NT"

# ala4 water extra production (third system in the outline)
run python3 run_md.py --system ala4_water --length 200 --nt "$NT"
run python3 run_md.py --system ala4_water --length 500 --nt "$NT"
run python3 run_md.py --system ala4_vacuum --length 200 --nt "$NT"
run python3 run_md.py --system ala4_vacuum --length 500 --nt "$NT"

run python3 hybrid08_run_campaign.py --analyze-only

echo "============================================================"
echo "[$(date '+%F %T')] GPU night exit"
echo "============================================================"

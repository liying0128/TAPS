#!/usr/bin/env bash
# Two CLN025 first-hit replicates (TAPS / LAST / Least-counts), same protocol as stage13.
# GPU stream: all six campaigns (original used GPU). CPU is left for cpu-night / cpu-fill.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
OUT="$ROOT/analysis/cln025_unfolded"
mkdir -p "$OUT"
LOG="$OUT/firsthit_reps.log"
export PYTHONUNBUFFERED=1
NT=8

exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] CLN025 first-hit replicates  pid=$$"
echo "protocol: init=10 ns  budget=82 ns  rounds=12  seeds=6  short=1 ns"
echo "methods: taps, last, density   GPU nt=$NT"
echo "============================================================"

run() {
  echo
  echo "----- [$(date '+%F %T')] $* -----"
  if ! "$@"; then
    echo "[$(date '+%F %T')] FAILED (continue): $*"
    return 1
  fi
}

COMMON=(
  --gpu --nt "$NT"
  --init-ns 10 --budget-ns 82 --max-rounds 12 --n-seeds 6
  --short-ps 1000 --window-ps 50 --horizon-ps 200 --stride-ps 10
  --nbins 24 --min-nm 0.10 --epochs 12
)

run python3 stage13_cln025_discover.py --check --tag-prefix discover_s1 --seed 1 --methods taps,last,density "${COMMON[@]}"
run python3 stage13_cln025_discover.py --tag-prefix discover_s1 --seed 1 --methods taps,last,density "${COMMON[@]}"
run python3 compare_cln_firsthit_reps.py

run python3 stage13_cln025_discover.py --tag-prefix discover_s2 --seed 2 --methods taps,last,density "${COMMON[@]}"
run python3 compare_cln_firsthit_reps.py

echo "============================================================"
echo "[$(date '+%F %T')] CLN025 first-hit replicates exit"
echo "report: $OUT/firsthit_reps_report.txt"
echo "============================================================"

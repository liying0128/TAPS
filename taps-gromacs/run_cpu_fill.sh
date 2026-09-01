#!/usr/bin/env bash
# Extra CPU queue for the ~15 h window (outline §12 / §13).
# Runs in parallel with cpu-night and the GPU hybrid. CPU mdrun uses -pin off.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
OUT="$ROOT/analysis/hybrid"
mkdir -p "$OUT"
LOG="$OUT/cpu_fill.log"
export PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=""
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY

exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] CPU fill start  pid=$$"
echo "============================================================"

C7AX="$ROOT/systems/alanine_dipeptide/vacuum/seeds/c7ax.gro"
CORES=8-31

run_one() {
  local name=$1
  shift
  echo
  echo "===== [$name] START $(date '+%F %T')  $* ====="
  if ! taskset -c "$CORES" "$@"; then
    echo "===== [$name] FAILED $(date '+%F %T') ====="
    return 1
  fi
  echo "===== [$name] DONE $(date '+%F %T') ====="
}

# --- immediately: larger CPU productions so the cores are not idle ---
run_one ala4_water_200 python3 run_md.py --system ala4_water --length 200 --cpu --nt 8 &
PID_ALA4W=$!
run_one cln025_water_200 python3 run_md.py --system cln025_water --length 200 --cpu --nt 8 &
PID_CLNW=$!

# --- §12.2 vacuum discovery, no C7ax injection (3 methods in parallel) ---
run_one disc_taps python3 stage12_discover_last.py --cpu --nt 4 --tag-prefix night_disc \
  --methods taps --init-ns 2 --budget-ns 82 --n-seeds 4 --short-ps 1000 --max-rounds 20 &
PID_DT=$!
run_one disc_last python3 stage12_discover_last.py --cpu --nt 4 --tag-prefix night_disc \
  --methods last --init-ns 2 --budget-ns 82 --n-seeds 4 --short-ps 1000 --max-rounds 20 &
PID_DL=$!
run_one disc_lc python3 stage12_discover_last.py --cpu --nt 4 --tag-prefix night_disc \
  --methods density --init-ns 2 --budget-ns 82 --n-seeds 4 --short-ps 1000 --max-rounds 20 &
PID_DC=$!

echo "[$(date '+%F %T')] waiting for vacuum discovery (heavy cMD continues in background)"
fail=0
for p in $PID_DT $PID_DL $PID_DC; do
  if ! wait "$p"; then fail=1; fi
done
echo "[$(date '+%F %T')] vacuum discovery finished (fail=$fail)"

# --- §12.3 known-rare exploitation with C7ax injection ---
if [[ -f "$C7AX" ]]; then
  run_one exploit_last python3 stage07_multi_round.py --system ala2_vacuum --tag night_exploit_last --strategy last \
    --cpu --nt 4 --init-ns 2 --budget-ns 42 --max-rounds 10 --n-seeds 4 \
    --short-ps 1000 --short-mdp md_short_1ns_vacuum.mdp --extra-init "$C7AX" &
  PID_EL=$!
  run_one exploit_taps python3 stage07_multi_round.py --system ala2_vacuum --tag night_exploit_taps --strategy full \
    --cpu --nt 4 --init-ns 2 --budget-ns 42 --max-rounds 10 --n-seeds 4 \
    --short-ps 1000 --short-mdp md_short_1ns_vacuum.mdp --extra-init "$C7AX" --epochs 8 &
  PID_ET=$!
  run_one exploit_lc python3 stage07_multi_round.py --system ala2_vacuum --tag night_exploit_lc --strategy density \
    --cpu --nt 4 --init-ns 2 --budget-ns 42 --max-rounds 10 --n-seeds 4 \
    --short-ps 1000 --short-mdp md_short_1ns_vacuum.mdp --extra-init "$C7AX" &
  PID_EC=$!
  for p in $PID_EL $PID_ET $PID_EC; do
    wait "$p" || true
  done
else
  echo "missing $C7AX — skip exploitation campaigns"
fi

echo "[$(date '+%F %T')] waiting for first-wave ala4/CLN CPU productions"
wait "$PID_ALA4W" || true
wait "$PID_CLNW" || true

# --- keep the machine busy if GPU/CPU night are still running ---
run_one ala4_vacuum_200 python3 run_md.py --system ala4_vacuum --length 200 --cpu --nt 8
run_one ala4_water_500 python3 run_md.py --system ala4_water --length 500 --cpu --nt 12
run_one cln025_water_500 python3 run_md.py --system cln025_water --length 500 --cpu --nt 12

echo "============================================================"
echo "[$(date '+%F %T')] CPU fill exit"
echo "============================================================"

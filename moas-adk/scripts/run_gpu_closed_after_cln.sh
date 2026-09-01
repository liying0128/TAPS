#!/usr/bin/env bash
# After CLN seed=3 releases the GPU, resume AdK closed 200 ns from the CPU checkpoint.
# Do not start this on the GPU while run_cln_seed3.sh is still running.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOAS_CLN="$(cd "$ROOT/../moas-gromacs" && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/gpu_closed_200ns.log"
mkdir -p "$ROOT/logs"
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"

wait_for() {
  local desc="$1"
  shift
  echo "[$(date '+%F %T')] waiting: $desc"
  while "$@"; do
    sleep 30
  done
  echo "[$(date '+%F %T')] ready: $desc"
}

cln_still_running() {
  pgrep -f '[b]ash run_cln_seed3.sh' >/dev/null 2>&1 \
    || pgrep -f '[p]ython3 stage13_cln025_discover.py' >/dev/null 2>&1
}

cpu_adk_still_running() {
  pgrep -f '[p]ython3 run_md.py --system adk_closed --length 200 --cpu' >/dev/null 2>&1
}

exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] AdK closed GPU resume waiter start  pid=$$"
echo "============================================================"

wait_for "AdK CPU 200 ns to stop" cpu_adk_still_running
wait_for "CLN seed=3 GPU queue to finish" cln_still_running

# Avoid colliding with a leftover CLN mdrun
sleep 5
echo "[$(date '+%F %T')] resuming adk_closed 200 ns on GPU  nt=$NT"
python3 run_md.py --system adk_closed --length 200 --gpu --nt "$NT"
echo "[$(date '+%F %T')] AdK closed GPU resume exit"

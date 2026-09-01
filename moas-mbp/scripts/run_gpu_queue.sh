#!/usr/bin/env bash
# GPU queue: EM/eq if needed, 20 ns open init, then Random / LAST / LC / MOAS-static (200 ns each).
# Also launched automatically after CLN seed=3 + AdK closed GPU resume
# (tmux moas:adk-gpu, scripts/run_gpu_chain_after_cln.sh in moas-adk).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/gpu_queue.log"
mkdir -p "$ROOT/logs"
unset CUDA_VISIBLE_DEVICES
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"
export NT
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] MBP GPU queue start  pid=$$  nt=$NT"
echo "============================================================"
bash "$ROOT/scripts/run_em_eq.sh"
bash "$ROOT/scripts/run_cmd_init.sh"
bash "$ROOT/scripts/run_discover.sh"
echo "[$(date '+%F %T')] MBP GPU queue exit"

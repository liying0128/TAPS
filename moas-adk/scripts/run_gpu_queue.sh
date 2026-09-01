#!/usr/bin/env bash
# GPU queue: 20 ns open init, then Random / LAST / LC / MOAS-static (200 ns each).
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
echo "[$(date '+%F %T')] AdK GPU queue start  pid=$$  nt=$NT"
echo "============================================================"
bash "$ROOT/scripts/run_cmd_init.sh"
bash "$ROOT/scripts/run_discover.sh"
echo "[$(date '+%F %T')] AdK GPU queue exit"

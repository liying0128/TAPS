#!/usr/bin/env bash
# CPU filler: 200 ns unbiased cMD from the closed NPT box.
# Separate files from the GPU open-start queue; uses leftover cores (--pin off).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/cpu_closed_200ns.log"
mkdir -p "$ROOT/logs"
export CUDA_VISIBLE_DEVICES=""
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-14}"
export NT
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] AdK CPU closed 200 ns start  pid=$$  nt=$NT"
echo "============================================================"
python3 run_md.py --system adk_closed --length 200 --cpu --nt "$NT"
echo "[$(date '+%F %T')] AdK CPU closed 200 ns exit"

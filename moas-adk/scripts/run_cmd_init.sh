#!/usr/bin/env bash
# 20 ns unbiased cMD from the open NPT box. Adaptive campaigns use this as init.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
NT="${NT:-16}"
python3 run_md.py --system adk_open --length 20 --gpu --nt "$NT"
python3 adk_angles.py --refs
echo "Init cMD done. Next: bash scripts/run_discover.sh"

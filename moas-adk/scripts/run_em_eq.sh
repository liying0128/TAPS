#!/usr/bin/env bash
# Equilibrate apo AdK (EM + 1 ns NVT + 1 ns NPT). Open is required; closed is the angle reference.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
NT="${NT:-16}"
python3 run_md.py --system adk_open --length 0 --gpu --nt "$NT"
python3 run_md.py --system adk_closed --length 0 --gpu --nt "$NT"
echo "Equilibration done. Next: bash scripts/run_cmd_init.sh"

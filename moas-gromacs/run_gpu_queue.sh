#!/usr/bin/env bash
# MOAS GPU queue on the RTX 4090. CLN025 only. No alanine peptides.
#
# 1) Finish native-start 500 ns cMD (resume from the CPU checkpoint).
# 2) Word-doc baselines that are still missing: Random, then MOAS-static
#    (novelty + LAST boundary + closer-to-fold proxy), 82 ns, 3 seeds.
set -u
MOAS="$(cd "$(dirname "$0")" && pwd)"
TAPS="$(cd "$MOAS/../taps-gromacs" && pwd)"
LOGDIR="$MOAS/logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/gpu_queue.log"

unset CUDA_VISIBLE_DEVICES
unset OMP_NUM_THREADS
unset GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1

exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] MOAS GPU queue start  pid=$$  GPU=$(nvidia-smi -L 2>/dev/null | head -1)"
echo "============================================================"

run() {
  echo
  echo "===== $* ====="
  echo "[$(date '+%F %T')] START"
  if "$@"; then
    echo "[$(date '+%F %T')] DONE"
    return 0
  fi
  echo "[$(date '+%F %T')] FAILED"
  return 1
}

# --- 1. native folded-start 500 ns cMD (files live in taps-gromacs; same inode after link) ---
cd "$TAPS"
run python3 run_md.py --system cln025_water --length 500 --gpu --nt 16
# keep MOAS tree in sync
mkdir -p "$MOAS/systems/chignolin_cln025/water/runs"
for f in "$TAPS/systems/chignolin_cln025/water/runs"/md_500ns.*; do
  base=$(basename "$f")
  dest="$MOAS/systems/chignolin_cln025/water/runs/$base"
  if [[ ! -e "$dest" ]]; then
    cp -l "$f" "$dest" 2>/dev/null || cp -a "$f" "$dest"
  fi
done

# --- 2. Word-doc adaptive campaigns (unfolded CLN025, 82 ns each, GPU) ---
cd "$TAPS"
for seed in 0 1 2; do
  prefix="moas"
  if [[ "$seed" != 0 ]]; then
    prefix="moas_s${seed}"
  fi
  run python3 stage13_cln025_discover.py --gpu --nt 16 --seed "$seed" \
    --methods random --tag-prefix "$prefix" \
    --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12
  run python3 stage13_cln025_discover.py --gpu --nt 16 --seed "$seed" \
    --methods moas --tag-prefix "$prefix" \
    --init-ns 10 --budget-ns 82 --n-seeds 6 --short-ps 1000 --max-rounds 12
done

echo "============================================================"
echo "[$(date '+%F %T')] MOAS GPU queue exit"
echo "============================================================"

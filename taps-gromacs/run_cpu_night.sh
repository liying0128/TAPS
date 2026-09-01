#!/usr/bin/env bash
# CPU night queue (Workflow §10 / §12). Does NOT touch the GPU.
# Pin to cores 8-31 so the current hybrid mdrun can keep 0-7.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
OUT="$ROOT/analysis/hybrid"
mkdir -p "$OUT"
LOG="$OUT/cpu_night.log"
export PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=""
unset OMP_NUM_THREADS
NT=20

exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] CPU night start  pid=$$"
echo "============================================================"

run() {
  echo
  echo "----- [$(date '+%F %T')] $* -----"
  if ! taskset -c 8-31 "$@"; then
    echo "[$(date '+%F %T')] FAILED (continue): $*"
  fi
}

# §12.2 ala2 vacuum discovery, no C7ax injection, longer budget
run python3 stage12_discover_last.py --cpu --nt 8 --tag-prefix night_disc \
  --init-ns 2 --budget-ns 82 --n-seeds 4 --short-ps 1000 --max-rounds 20

# §12.3 known-rare exploitation with C7ax injection
run python3 stage07_multi_round.py --system ala2_vacuum --tag night_exploit_last --strategy last \
  --cpu --nt 8 --init-ns 2 --budget-ns 42 --max-rounds 10 --n-seeds 4 \
  --short-ps 1000 --short-mdp md_short_1ns_vacuum.mdp --extra-init systems/alanine_dipeptide/vacuum/seeds/c7ax.gro
run python3 stage07_multi_round.py --system ala2_vacuum --tag night_exploit_taps --strategy full \
  --cpu --nt 8 --init-ns 2 --budget-ns 42 --max-rounds 10 --n-seeds 4 \
  --short-ps 1000 --short-mdp md_short_1ns_vacuum.mdp --extra-init systems/alanine_dipeptide/vacuum/seeds/c7ax.gro
run python3 stage07_multi_round.py --system ala2_vacuum --tag night_exploit_lc --strategy density \
  --cpu --nt 8 --init-ns 2 --budget-ns 42 --max-rounds 10 --n-seeds 4 \
  --short-ps 1000 --short-mdp md_short_1ns_vacuum.mdp --extra-init systems/alanine_dipeptide/vacuum/seeds/c7ax.gro

# ala2 explicit-water campaigns (fills CPU for hours)
run python3 stage01_extract_dihedrals.py --system ala2_water
run python3 stage07_multi_round.py --system ala2_water --tag night_last --strategy last \
  --cpu --nt "$NT" --init-ns 10 --budget-ns 58 --max-rounds 12 --n-seeds 4 \
  --short-ps 1000 --short-mdp md_short_1ns.mdp --window-ps 50 --horizon-ps 200 --stride-ps 10
run python3 stage07_multi_round.py --system ala2_water --tag night_lc --strategy density \
  --cpu --nt "$NT" --init-ns 10 --budget-ns 58 --max-rounds 12 --n-seeds 4 \
  --short-ps 1000 --short-mdp md_short_1ns.mdp --window-ps 50 --horizon-ps 200 --stride-ps 10
run python3 stage07_multi_round.py --system ala2_water --tag night_taps --strategy full \
  --cpu --nt "$NT" --init-ns 10 --budget-ns 58 --max-rounds 12 --n-seeds 4 \
  --short-ps 1000 --short-mdp md_short_1ns.mdp --window-ps 50 --horizon-ps 200 --stride-ps 10 --epochs 8

echo "============================================================"
echo "[$(date '+%F %T')] CPU night exit"
echo "============================================================"

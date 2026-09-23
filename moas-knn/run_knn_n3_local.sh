#!/usr/bin/env bash
# After local MBP seed=2 four-method finishes: CLN kNN s1+s2, AdK kNN s2, MBP kNN s2.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TAPS="$(cd "$HERE/.." && pwd)"
if [[ -f /usr/local/gromacs/bin/GMXRC ]]; then
  set +u
  # shellcheck disable=SC1091
  source /usr/local/gromacs/bin/GMXRC
  set -u
fi
export PATH="/usr/local/gromacs/bin:${PATH}"
export GMX="/usr/local/gromacs/bin/gmx"
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"
export NT
LOG="$HERE/logs/knn_n3_local.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] kNN n=3 local queue  CLN s1,s2 + AdK s2 + MBP s2  nt=$NT"
echo "============================================================"

cd "$TAPS/taps-gromacs"
python3 stage13_cln025_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- CLN kNN-AS seed=1 ----"
SEED=1 bash scripts/run_knn.sh
echo "[$(date '+%F %T')] ---- CLN kNN-AS seed=2 ----"
SEED=2 bash scripts/run_knn.sh

cd "$TAPS/moas-adk"
python3 stage_adk_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- AdK kNN-AS seed=2 ----"
SEED=2 bash scripts/run_knn.sh

cd "$TAPS/moas-mbp"
python3 stage_mbp_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- MBP kNN-AS seed=2 ----"
SEED=2 bash scripts/run_knn.sh

echo "[$(date '+%F %T')] kNN n=3 local queue exit"

#!/usr/bin/env bash
# After 55 MBP kNN seed=0 finishes: AdK kNN s1 + MBP kNN s1.
# CLN kNN s1/s2 stay on 244 (55 has no CLN init trajectory).
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
if [[ -f /home/ly/miniconda3/etc/profile.d/conda.sh ]]; then
  set +u
  # shellcheck disable=SC1091
  source /home/ly/miniconda3/etc/profile.d/conda.sh
  conda activate base 2>/dev/null || true
  set -u
fi
export PATH="/usr/local/gromacs/bin:${PATH}"
export GMX="/usr/local/gromacs/bin/gmx"
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"
export NT
LOG="$HERE/logs/knn_n3_55.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] kNN n=3 55 queue  AdK s1 + MBP s1  nt=$NT"
echo "============================================================"

cd "$TAPS/moas-adk"
python3 stage_adk_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- AdK kNN-AS seed=1 ----"
SEED=1 bash scripts/run_knn.sh

cd "$TAPS/moas-mbp"
python3 stage_mbp_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- MBP kNN-AS seed=1 ----"
SEED=1 bash scripts/run_knn.sh

echo "[$(date '+%F %T')] kNN n=3 55 queue exit"

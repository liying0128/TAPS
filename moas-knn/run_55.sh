#!/usr/bin/env bash
# kNN-AS on lan55 after 173 handoff: resume AdK, then MBP. Skip CLN (already done).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
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
SEED="${SEED:-0}"
export NT SEED
TAPS="$(cd "$HERE/.." && pwd)"
LOG="$HERE/logs/run_55_seed${SEED}.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] kNN-AS 55 queue start  seed=$SEED  nt=$NT  gmx=$(command -v gmx)"
gmx --version 2>&1 | head -n 1
df -h / | tail -n 1
echo "============================================================"

cd "$TAPS/moas-adk"
python3 stage_adk_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- AdK kNN-AS ----"
bash scripts/run_knn.sh

cd "$TAPS/moas-mbp"
python3 stage_mbp_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- MBP kNN-AS ----"
bash scripts/run_knn.sh

echo "[$(date '+%F %T')] kNN-AS 55 queue exit"

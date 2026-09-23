#!/usr/bin/env bash
# 173 queue: kNN-AS only, CLN025 → AdK → MBP. Same budgets as the four-method campaigns.
# Does not start Random/LAST/LC/static. Resume-safe via history.json.
# Usage on 173:  NT=4 SEED=0 bash /home/ly/TAPS/moas-knn/run_173.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/env_remote.sh"
NT="${NT:-$(nproc)}"
SEED="${SEED:-0}"
export NT SEED
TAPS="$(cd "$HERE/.." && pwd)"
LOG="$HERE/logs/run_173_seed${SEED}.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] kNN-AS 173 queue start  seed=$SEED  nt=$NT  gmx=$(command -v gmx)"
gmx --version 2>&1 | head -n 1
python3 -c "import numpy; print('numpy', numpy.__version__)"
df -h / | tail -n 1
echo "============================================================"

cd "$TAPS/taps-gromacs"
python3 stage13_cln025_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- CLN025 kNN-AS ----"
bash scripts/run_knn.sh

cd "$TAPS/moas-adk"
python3 stage_adk_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- AdK kNN-AS ----"
bash scripts/run_knn.sh

cd "$TAPS/moas-mbp"
python3 stage_mbp_discover.py --check --methods knn
echo "[$(date '+%F %T')] ---- MBP kNN-AS ----"
bash scripts/run_knn.sh

echo "[$(date '+%F %T')] kNN-AS 173 queue exit"

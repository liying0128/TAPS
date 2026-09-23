#!/usr/bin/env bash
# After local MBP kNN s2 finishes, start AdK+MBP ablation n=1 on this machine only.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/logs/wait_ablation_local.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1
KNN_PY='stage_mbp_discover.py --gpu --nt 16 --seed 2 --tag-prefix mbp_s2 --methods knn'
echo "[$(date '+%F %T')] waiter start: block until MBP kNN s2 finishes"
while pgrep -f "$KNN_PY" >/dev/null 2>&1; do
  echo "[$(date '+%F %T')] still running MBP kNN s2"
  sleep 60
done
echo "[$(date '+%F %T')] MBP kNN s2 gone; wait 8s"
sleep 8

# Free NVMe for ablation: drop regenerable knn analysis scratch, archive knn xtc if data has room.
KNN_A=/home/ly/TAPS/moas-mbp/analysis/mbp_open/campaigns/mbp_s2_knn
KNN_S=/home/ly/TAPS/moas-mbp/systems/mbp/water_open/adaptive/campaigns/mbp_s2_knn
DATA_S=/home/ly/data/TAPS/moas-mbp/systems/mbp/water_open/adaptive/campaigns/mbp_s2_knn
if [[ -d "$KNN_A" && ! -L "$KNN_A" ]]; then
  echo "[$(date '+%F %T')] drop scratch $KNN_A"
  find "$KNN_A" -type d -name 'seed_*_scratch' -prune -print0 | xargs -0 -r rm -rf
fi
if [[ -d "$KNN_S" && ! -L "$KNN_S" ]]; then
  avail=$(df -B1 --output=avail /home/ly/data | tail -1 | tr -d ' ')
  need=$((130 * 1024 * 1024 * 1024))
  if (( avail >= need )); then
    echo "[$(date '+%F %T')] archive $KNN_S -> $DATA_S"
    mkdir -p "$(dirname "$DATA_S")"
    rsync -a "$KNN_S/" "$DATA_S/"
    rm -rf "$KNN_S"
    ln -s "$DATA_S" "$KNN_S"
  else
    echo "[$(date '+%F %T')] skip archive knn systems; data avail=$avail"
  fi
fi
df -h / /home/ly/data | tail -n +1
NT=16 bash "$HERE/run_ablation_local.sh"
echo "[$(date '+%F %T')] waiter exit"

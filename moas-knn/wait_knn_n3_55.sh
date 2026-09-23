#!/usr/bin/env bash
# Wait until current 55 kNN seed=0 queue (run_55.sh) exits, then AdK/MBP seed=1.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/logs/wait_knn_n3_55.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1
echo "[$(date '+%F %T')] waiter start: block until MBP kNN seed=0 python exits"
while pgrep -f 'stage_mbp_discover.py --gpu --nt 16 --seed 0 --tag-prefix mbp --methods knn' >/dev/null 2>&1 \
  || pgrep -f 'stage_adk_discover.py --gpu --nt 16 --seed 0 --tag-prefix adk --methods knn' >/dev/null 2>&1; do
  echo "[$(date '+%F %T')] still running kNN seed=0 on 55"
  sleep 60
done
echo "[$(date '+%F %T')] seed=0 queue gone; wait 8s then start kNN seed=1"
sleep 8
NT=16 bash "$HERE/run_knn_n3_55.sh"
echo "[$(date '+%F %T')] waiter exit"

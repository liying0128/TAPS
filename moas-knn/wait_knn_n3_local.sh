#!/usr/bin/env bash
# Wait until local MBP seed=2 four-method python exits, then start kNN n=3.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/logs/wait_knn_n3_local.log"
mkdir -p "$HERE/logs"
exec > >(tee -a "$LOG") 2>&1
PATTERN='stage_mbp_discover.py --gpu --nt 16 --seed 2 --tag-prefix mbp_s2 --methods random last density moas'
echo "[$(date '+%F %T')] waiter start: block until four-method MBP s2 finishes"
while pgrep -f "$PATTERN" >/dev/null 2>&1; do
  echo "[$(date '+%F %T')] still running four-method MBP s2"
  sleep 60
done
echo "[$(date '+%F %T')] four-method MBP s2 gone; wait 8s then start kNN n=3"
sleep 8
# Do not archive mbp_s2_last (wedged seeds_r32). Move finished LC/static off NVMe if present.
DATA=/home/ly/data/TAPS
archive_tree() {
  local src="$1" dest="$2"
  if [[ -L "$src" ]]; then
    echo "already symlink $src"
    return 0
  fi
  if [[ ! -d "$src" ]]; then
    return 0
  fi
  echo "[$(date '+%F %T')] archive $src -> $dest"
  mkdir -p "$(dirname "$dest")"
  rsync -a "$src/" "$dest/"
  rm -rf "$src"
  ln -s "$dest" "$src"
}
for name in mbp_s2_random mbp_s2_lc mbp_s2_static; do
  archive_tree \
    "/home/ly/TAPS/moas-mbp/analysis/mbp_open/campaigns/$name" \
    "$DATA/moas-mbp/analysis/mbp_open/campaigns/$name" || true
  archive_tree \
    "/home/ly/TAPS/moas-mbp/systems/mbp/water_open/adaptive/campaigns/$name" \
    "$DATA/moas-mbp/systems/mbp/water_open/adaptive/campaigns/$name" || true
done
df -h / | tail -n 1
NT=16 bash "$HERE/run_knn_n3_local.sh"
echo "[$(date '+%F %T')] waiter exit"

#!/usr/bin/env bash
# Free NVMe for remaining static + kNN n=3. Do not touch live mbp_s2_static.
# 1) Drop regenerable analysis scratch (prot.xtc) on finished campaigns.
# 2) Move finished LC / LAST trajectories to /home/ly/data and symlink.
set -euo pipefail
LOG=/home/ly/data/TAPS/archive_free_space.log
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
ionice -c 3 -p $$ 2>/dev/null || true
renice 10 $$ >/dev/null 2>&1 || true

DATA=/home/ly/data/TAPS
NVME_A=/home/ly/TAPS/moas-mbp/analysis/mbp_open/campaigns
NVME_S=/home/ly/TAPS/moas-mbp/systems/mbp/water_open/adaptive/campaigns
DATA_A=$DATA/moas-mbp/analysis/mbp_open/campaigns
DATA_S=$DATA/moas-mbp/systems/mbp/water_open/adaptive/campaigns

log() { echo "[$(date '+%F %T')] $*"; }
df_both() { df -h / /home/ly/data | tail -n +1; }

drop_scratch() {
  local root="$1"
  if [[ ! -d "$root" ]]; then
    log "skip scratch, missing $root"
    return 0
  fi
  log "drop scratch under $root"
  find "$root" -type d -name 'seed_*_scratch' -prune -print0 | xargs -0 -r rm -rf
}

archive_tree() {
  local src="$1" dest="$2"
  if [[ -L "$src" ]]; then
    log "already symlink $src"
    return 0
  fi
  if [[ ! -d "$src" ]]; then
    log "missing $src"
    return 0
  fi
  log "rsync $src -> $dest"
  mkdir -p "$(dirname "$dest")"
  rsync -a --info=stats2 "$src/" "$dest/"
  rm -rf "$src"
  ln -s "$dest" "$src"
  log "symlinked $src"
}

log "========== free-space start =========="
df_both

# Finished only. Live static writes systems/ + current-round analysis scratch.
drop_scratch "$NVME_A/mbp_s2_lc/adaptive"
drop_scratch "$NVME_A/mbp_s2_last/adaptive"
log "after NVMe scratch drop:"
df_both

# Archived seed=0 / s2_random on data: same scratch is duplicate of systems xtc.
for name in mbp_random mbp_last mbp_lc mbp_static mbp_s2_random; do
  drop_scratch "$DATA_A/$name/adaptive"
done
log "after data scratch drop:"
df_both

archive_tree "$NVME_A/mbp_s2_lc" "$DATA_A/mbp_s2_lc"
archive_tree "$NVME_S/mbp_s2_lc" "$DATA_S/mbp_s2_lc"
# LAST analysis has wedged seeds_r32 — move adaptive trajectories only.
archive_tree "$NVME_S/mbp_s2_last" "$DATA_S/mbp_s2_last"
if [[ -d "$NVME_A/mbp_s2_last/adaptive" && ! -L "$NVME_A/mbp_s2_last" ]]; then
  archive_tree "$NVME_A/mbp_s2_last/adaptive" "$DATA_A/mbp_s2_last/adaptive"
fi

log "========== free-space done =========="
df_both
timeout 10 du -sh "$NVME_A"/mbp_s2_* "$NVME_S"/mbp_s2_* 2>/dev/null || true

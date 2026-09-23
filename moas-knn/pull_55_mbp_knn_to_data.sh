#!/usr/bin/env bash
# Pull finished 55-system-disk MBP kNN trajectories onto 244 /home/ly/data.
# Local data has ~282G free; leave ~40G margin → move ~240G (mbp_knn + mbp_s1_knn systems).
# Also drop regenerable seed_*_scratch on 55 finished MBP analysis (does not fill local).
set -euo pipefail

LOG=/home/ly/data/TAPS/from_55/pull_55.log
DEST=/home/ly/data/TAPS/from_55
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new lan55)
RSYNC_SSH='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new'

A55=/home/ly/TAPS/moas-mbp/analysis/mbp_open/campaigns
S55=/home/ly/TAPS/moas-mbp/systems/mbp/water_open/adaptive/campaigns
MOVE_CAMPAIGNS=(mbp_knn mbp_s1_knn)

mkdir -p "$DEST"
exec >>"$LOG" 2>&1
ionice -c 3 -p $$ 2>/dev/null || true
renice 10 $$ >/dev/null 2>&1 || true

log() { echo "[$(date '+%F %T')] $*"; }
df_local() { df -h / /home/ly/data; }
df_55() { "${SSH[@]}" 'df -h / /home/ly/data'; }

bytes_free_data() {
  df -B1 --output=avail /home/ly/data | tail -1 | tr -d ' '
}

verify_tree() {
  local src="$1" dest="$2"
  local sb db sc dc
  sb=$("${SSH[@]}" "du -sb --apparent-size '$src'" | awk '{print $1}')
  db=$(du -sb --apparent-size "$dest" | awk '{print $1}')
  sc=$("${SSH[@]}" "find '$src' -printf '.' | wc -c")
  dc=$(find "$dest" -printf '.' | wc -c)
  log "verify $src  bytes=$sb files=$sc"
  log "verify $dest bytes=$db files=$dc"
  if [[ "$sb" != "$db" || "$sc" != "$dc" ]]; then
    log "VERIFY FAIL $src"
    return 1
  fi
}

write_marker() {
  local remote="$1" localpath="$2"
  local when
  when=$(date '+%F %T')
  "${SSH[@]}" "rm -rf '$remote' && mkdir -p '$remote' && printf '%s\n' \
    'Moved ${when} from lan55 system disk (/) to:' \
    '  ${localpath}' \
    'Do not re-run this campaign on 55 without copying the tree back.' \
    > '$remote/MOVED_TO_192.168.31.244.txt'"
}

log "========== pull_55 start =========="
df_local
df_55

free=$(bytes_free_data)
need=$((250 * 1024 * 1024 * 1024))
if (( free < need )); then
  log "ABORT: /home/ly/data has $free bytes free, need >= $need"
  exit 1
fi

log "drop regenerable scratch on 55 finished MBP analysis"
"${SSH[@]}" bash -s <<'EOS'
set -euo pipefail
A=/home/ly/TAPS/moas-mbp/analysis/mbp_open/campaigns
for name in mbp_knn mbp_s1_knn mbp_s1_lc mbp_s1_static; do
  root="$A/$name"
  if [[ -d "$root" && ! -L "$root" ]]; then
    echo "drop scratch $root"
    find "$root" -type d -name 'seed_*_scratch' -prune -print0 | xargs -0 -r rm -rf
  else
    echo "skip scratch $root"
  fi
done
df -h /
EOS
log "after 55 scratch drop:"
df_55

for name in "${MOVE_CAMPAIGNS[@]}"; do
  src="$S55/$name"
  dest="$DEST/moas-mbp/systems/mbp/water_open/adaptive/campaigns/$name"
  log "rsync systems $name"
  mkdir -p "$dest"
  rsync -a --partial --info=stats2 -e "$RSYNC_SSH" "lan55:$src/" "$dest/"
  verify_tree "$src" "$dest"
  asrc="$A55/$name"
  adest="$DEST/moas-mbp/analysis/mbp_open/campaigns/$name"
  log "rsync slim analysis $name"
  mkdir -p "$adest"
  rsync -a --partial --info=stats2 -e "$RSYNC_SSH" "lan55:$asrc/" "$adest/"
  verify_tree "$asrc" "$adest"
done

log "verified; deleting moved systems on 55 (keep slim analysis/history)"
for name in "${MOVE_CAMPAIGNS[@]}"; do
  write_marker "$S55/$name" "$DEST/moas-mbp/systems/mbp/water_open/adaptive/campaigns/$name"
done

log "========== pull_55 done =========="
df_local
df_55
du -sh "$DEST"/moas-mbp/systems/mbp/water_open/adaptive/campaigns/* \
       "$DEST"/moas-mbp/analysis/mbp_open/campaigns/* 2>/dev/null || true

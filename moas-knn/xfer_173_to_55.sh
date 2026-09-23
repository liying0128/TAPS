#!/usr/bin/env bash
# Stop kNN-AS on 173, stream campaigns 173→55 (this host is a pipe only, no disk
# staging), then resume AdK then MBP on 55.
set -euo pipefail
LOG="${LOG:-/home/ly/TAPS/moas-knn/logs/knn_xfer_173_55.log}"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
SSH_OPTS=(-o IdentitiesOnly=yes -o ConnectTimeout=20 -o ServerAliveInterval=30 -o ServerAliveCountMax=120)
SSH173=(ssh "${SSH_OPTS[@]}" -i /home/ly/.ssh/id_ed25519_lan173 ly@10.27.138.173)
SSH55=(ssh "${SSH_OPTS[@]}" -i /home/ly/.ssh/id_ed25519_lan55 ly@192.168.31.55)
R55="ssh ${SSH_OPTS[*]} -i /home/ly/.ssh/id_ed25519_lan55"
TAPS=/home/ly/TAPS

pipe_tar() {
  local src_cd="$1" src_name="$2" dst_cd="$3"
  echo "[$(date '+%F %T')] stream ${src_cd}/${src_name} -> 55:${dst_cd}/"
  "${SSH173[@]}" "tar cf - -C $(printf '%q' "$src_cd") $(printf '%q' "$src_name")" \
    | "${SSH55[@]}" "mkdir -p $(printf '%q' "$dst_cd") && tar xf - -C $(printf '%q' "$dst_cd")"
}

echo "============================================================"
echo "[$(date '+%F %T')] kNN 173→55 stream handoff start (no local staging)"
echo "============================================================"

echo "[$(date '+%F %T')] stop 173 knn queue (leave tmux)"
"${SSH173[@]}" 'bash -s' << 'EOF'
set -e
pkill -TERM -f '/home/ly/TAPS/moas-knn/run_173.sh' 2>/dev/null || true
pkill -TERM -f 'moas-adk/scripts/run_knn.sh' 2>/dev/null || true
pkill -TERM -f 'moas-mbp/scripts/run_knn.sh' 2>/dev/null || true
pkill -TERM -f 'stage_adk_discover.py' 2>/dev/null || true
pkill -TERM -f 'stage_mbp_discover.py' 2>/dev/null || true
sleep 2
pkill -TERM -f 'gmx mdrun' 2>/dev/null || true
sleep 3
rm -rf /home/ly/TAPS/moas-adk/systems/adk/water_open/adaptive/campaigns/adk_knn/round10/seed_05
rm -rf /home/ly/TAPS/moas-adk/analysis/adk_open/campaigns/adk_knn/adaptive/round10/seed_05_scratch
rm -f /home/ly/TAPS/moas-adk/analysis/adk_open/campaigns/adk_knn/adaptive/round10/seed_05_cvs.npz
pgrep -af 'stage_adk_discover|gmx mdrun|run_173.sh|run_knn.sh' | grep -v grep || echo '173 jobs stopped'
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
if tmux has-session -t moas-mbp 2>/dev/null; then
  tmux send-keys -t moas-mbp:knn C-c 2>/dev/null || true
  sleep 0.3
  tmux send-keys -t moas-mbp:knn 'echo STOPPED_moved_to_lan55' C-m
fi
EOF

echo "[$(date '+%F %T')] rsync knn code 244 → 55 (scripts only)"
"${SSH55[@]}" 'mkdir -p /home/ly/TAPS/moas-adk/scripts /home/ly/TAPS/moas-mbp/scripts /home/ly/TAPS/moas-knn'
rsync -a -e "$R55" \
  "$TAPS/moas-adk/knn_as.py" \
  "$TAPS/moas-adk/stage_adk_discover.py" \
  ly@192.168.31.55:/home/ly/TAPS/moas-adk/
rsync -a -e "$R55" \
  "$TAPS/moas-adk/scripts/run_knn.sh" \
  ly@192.168.31.55:/home/ly/TAPS/moas-adk/scripts/
rsync -a -e "$R55" \
  "$TAPS/moas-mbp/knn_as.py" \
  "$TAPS/moas-mbp/stage_mbp_discover.py" \
  "$TAPS/moas-mbp/mbp_common.py" \
  ly@192.168.31.55:/home/ly/TAPS/moas-mbp/
rsync -a -e "$R55" \
  "$TAPS/moas-mbp/scripts/run_knn.sh" \
  ly@192.168.31.55:/home/ly/TAPS/moas-mbp/scripts/
rsync -a -e "$R55" "$TAPS/moas-knn/" ly@192.168.31.55:/home/ly/TAPS/moas-knn/
"${SSH55[@]}" 'chmod +x /home/ly/TAPS/moas-adk/scripts/run_knn.sh /home/ly/TAPS/moas-mbp/scripts/run_knn.sh /home/ly/TAPS/moas-knn/*.sh'

echo "[$(date '+%F %T')] stream campaigns 173 → 55 (pipe through 244, not stored)"
pipe_tar /home/ly/TAPS/moas-adk/analysis/adk_open/campaigns adk_knn \
  /home/ly/TAPS/moas-adk/analysis/adk_open/campaigns
pipe_tar /home/ly/TAPS/moas-adk/systems/adk/water_open/adaptive/campaigns adk_knn \
  /home/ly/TAPS/moas-adk/systems/adk/water_open/adaptive/campaigns
pipe_tar /home/ly/TAPS/taps-gromacs/analysis/cln025_unfolded/campaigns discover_knn \
  /home/ly/TAPS/taps-gromacs/analysis/cln025_unfolded/campaigns
pipe_tar /home/ly/TAPS/taps-gromacs/systems/chignolin_cln025/water_unfolded/adaptive/campaigns discover_knn \
  /home/ly/TAPS/taps-gromacs/systems/chignolin_cln025/water_unfolded/adaptive/campaigns

echo "[$(date '+%F %T')] start kNN queue on 55 tmux moas-adk:knn"
"${SSH55[@]}" 'bash -s' << 'EOF'
set -e
if ! tmux has-session -t moas-adk 2>/dev/null; then
  tmux new-session -d -s moas-adk -n knn
else
  if tmux list-windows -t moas-adk -F "#{window_name}" | grep -qx knn; then
    true
  else
    tmux new-window -t moas-adk -n knn
  fi
fi
tmux send-keys -t moas-adk:knn C-c || true
sleep 0.3
tmux send-keys -t moas-adk:knn 'cd /home/ly/TAPS/moas-knn && NT=16 SEED=0 bash run_55.sh' C-m
sleep 8
pgrep -af 'stage_adk_discover|run_55.sh|gmx mdrun' | grep -v grep || echo 'WARN: no knn process yet'
tmux capture-pane -t moas-adk:knn -p | tail -n 20
nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader
EOF

echo "[$(date '+%F %T')] handoff done"
echo "============================================================"

#!/usr/bin/env bash
# After CLN seed=3: resume AdK closed 200 ns on GPU, then the full MBP GPU queue.
# Lives in tmux (moas:adk-gpu). Closing Cursor/IDE does not stop this.
set -euo pipefail
ADK="$(cd "$(dirname "$0")/.." && pwd)"
MBP="$(cd "$ADK/../moas-mbp" && pwd)"
cd "$ADK"
LOG="$ADK/logs/gpu_chain.log"
mkdir -p "$ADK/logs" "$MBP/logs"
unset CUDA_VISIBLE_DEVICES OMP_NUM_THREADS GOMP_CPU_AFFINITY
export PYTHONUNBUFFERED=1
export GMX_MAXBACKUP=-1
NT="${NT:-16}"
export NT

wait_for() {
  local desc="$1"
  shift
  echo "[$(date '+%F %T')] waiting: $desc"
  while "$@"; do
    sleep 30
  done
  echo "[$(date '+%F %T')] ready: $desc"
}

cln_still_running() {
  pgrep -f '[b]ash run_cln_seed3.sh' >/dev/null 2>&1 \
    || pgrep -f '[p]ython3 stage13_cln025_discover.py' >/dev/null 2>&1
}

exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "[$(date '+%F %T')] GPU chain start  pid=$$  nt=$NT"
echo "  1) wait CLN seed=3"
echo "  2) AdK closed 200 ns resume (GPU)"
echo "  3) MBP EM/eq + 20 ns init + 4-method discover"
echo "============================================================"

wait_for "CLN seed=3 GPU queue to finish" cln_still_running
sleep 5

echo
echo "[$(date '+%F %T')] === AdK closed 200 ns GPU resume ==="
cd "$ADK"
python3 run_md.py --system adk_closed --length 200 --gpu --nt "$NT"
echo "[$(date '+%F %T')] AdK closed GPU resume done"

echo
echo "[$(date '+%F %T')] === MBP GPU queue ==="
cd "$MBP"
if [[ ! -f systems/mbp/water_open/ions.gro ]]; then
  echo "missing MBP ions.gro; run bash scripts/prepare_mbp.sh first" >&2
  exit 1
fi
bash "$MBP/scripts/run_gpu_queue.sh"
echo "[$(date '+%F %T')] GPU chain exit"

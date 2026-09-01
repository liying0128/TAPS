#!/usr/bin/env bash
# Real LAST→TAPS hybrid MD on CLN025 unfolded (Hybrid 08).
# Order: hybrid3 (75% LAST) → hybrid2 → hybrid1. Resumes if restarted.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
OUT="$ROOT/analysis/hybrid"
mkdir -p "$OUT"
LOG="$OUT/campaign.log"
export PYTHONUNBUFFERED=1

exec > >(tee -a "$LOG") 2>&1

echo "============================================================"
echo "[$(date '+%F %T')] hybrid campaign start  pid=$$  host=$(hostname)"
echo "cwd=$ROOT"
echo "============================================================"
nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv || true

python3 hybrid08_run_campaign.py --gpu
code=$?

echo "============================================================"
echo "[$(date '+%F %T')] hybrid campaign exit=$code"
echo "report: $OUT/hybrid_campaign_report.txt"
echo "============================================================"
exit "$code"

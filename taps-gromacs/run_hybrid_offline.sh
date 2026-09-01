#!/usr/bin/env bash
# Offline hybrid pipeline (Workflow §2–§10). No new MD.
# Run from taps-gromacs/:
#   bash run_hybrid_offline.sh
#   bash run_hybrid_offline.sh cln025
#   bash run_hybrid_offline.sh ala2

set -euo pipefail
cd "$(dirname "$0")"
SYS="${1:-both}"

echo "==== HYBRID 01  candidates + improved FEU novelty ===="
python3 hybrid01_build_candidates.py --system "$SYS"

echo "==== HYBRID 02  A/B/C ablation on FEU ===="
python3 hybrid02_ablate_feu.py --system "$SYS" --horizon 200
python3 hybrid02_ablate_feu.py --system "$SYS" --horizon 500
python3 hybrid02_ablate_feu.py --system "$SYS" --horizon 1000

echo "==== HYBRID 03  LAST vs TAPS complementarity ===="
python3 hybrid03_complement.py --system "$SYS" --horizon 200

echo "==== HYBRID 04  uncertainty calibration ===="
python3 hybrid04_uncertainty.py --system "$SYS" --horizon 200

echo "==== HYBRID 06  productive exploration (before stitch) ===="
python3 hybrid06_productive.py --system "$SYS"

echo "==== HYBRID 05  fixed LAST→TAPS replay ===="
python3 hybrid05_replay_hybrid.py --system "$SYS"

echo "==== HYBRID 07  novelty scorecard ===="
python3 hybrid07_novelty_audit.py --system "$SYS" --horizon 200

echo "done. reports in analysis/hybrid/"
ls -1 analysis/hybrid/*_{report,audit,scorecard}.txt analysis/hybrid/novelty_scorecard.txt 2>/dev/null || true

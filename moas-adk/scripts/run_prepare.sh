#!/usr/bin/env bash
# Build the AdK boxes (pdb2gmx, solvate, ions). Does not run MD.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/prepare_adk.sh"

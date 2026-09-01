#!/usr/bin/env python3
"""Shared paths and CLN025 protocol constants for MOAS."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
SYSTEMS = ROOT / "systems" / "chignolin_cln025"
UNFOLDED = SYSTEMS / "water_unfolded"
NATIVE = SYSTEMS / "water"

# Success protocol (design outline §1.1 / §9)
FOLD_RMSD_NM = 0.25
COMMIT_PS = 40.0
RMSD_MAX = 1.60
RG_MIN, RG_MAX = 0.45, 1.70

# Campaigns copied from taps-gromacs (post-hoc / dry-run pool)
LEGACY_CAMPAIGNS = UNFOLDED / "adaptive" / "campaigns"
LEGACY_ANALYSIS = DATA / "legacy" / "cln025_unfolded"
LEGACY_HYBRID = DATA / "legacy" / "hybrid_offline"

OBJECTIVE_NAMES = (
    "novelty",
    "boundary",
    "kinetic",
    "uncertainty",
    "commitment",
    "information_gain",
)

OPERATORS = (
    "last",
    "least_counts",
    "boundary",
    "kinetic",
    "commitment",
    "uncertainty",
    "random",
    "moas_weighted",
    "moas_pareto",
)

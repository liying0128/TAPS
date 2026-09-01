# MOAS — Multi-objective Adaptive Sampling (CLN025)

English working directory for **Multi-objective Adaptive Molecular Dynamics Sampling**.
主体系只有 **Chignolin CLN025**（显式水）。不再使用丙氨酸二肽 / 四肽。

This tree follows the MOAS design outline: independent objectives, configurable weights/policies, dry-run before new MD, and **committed fold** (residence ≥ 40 ps) as the discovery criterion. `first-hit` is reported but is not the success metric.

## Layout

```
moas-gromacs/
  systems/chignolin_cln025/   CLN025 topologies + completed MD (from taps-gromacs)
  shared/mdp/                 water MDP templates
  data/legacy/                existing CLN025 campaign analysis + offline tables
  data/candidates/            CLN candidate pool (npz) for Phase 1 replay
  representations/            RMSD/Rg, contacts, latent, TICA/VAMP
  objectives/                 novelty, boundary, kinetic, uncertainty, commitment, I.G.
  scoring/                    normalization, weighted utility, Pareto
  selection/                  diversity-aware seed selection
  policies/                   fixed / dynamic weights; later bandit
  budget/                     equal vs adaptive allocation under a hard cap
  models/                     logistic / RF / XGBoost first; DL optional
  simulation/                 GROMACS launcher (see also run_md.py)
  evaluation/                 commit protocol and metrics
  experiments/                YAML/JSON experiment configs
  results/                    per-round provenance (empty until Phase 1 runs)
  legacy_taps/                copied TAPS helper scripts (reference only)
```

## What was copied from `taps-gromacs`

Only CLN025. Trajectories (`*.xtc`) are **hard-linked** on the same disk so the 50 GB tree is not duplicated; topologies and MDP files are real copies.

| Asset | Role |
|---|---|
| `systems/.../water_unfolded/` | Main system: unfolded start, EM/NVT/NPT, cMD 100 ns + 500 ns |
| `systems/.../water_unfolded/adaptive/campaigns/` | LAST / LC / TAPS / Hybrid 82 ns campaigns + 3 seeds |
| `systems/.../water/` | Native/folded-start cMD (100 ns, 200 ns complete) |
| `data/legacy/cln025_unfolded/` | Per-campaign RMSD/Rg analysis and first-hit/commit reports |
| `data/legacy/hybrid_offline/` | CLN-only FEU ablation, complement, uncertainty, novelty tables |
| `data/candidates/cln_candidates.npz` | Offline candidate pool for post-hoc MOAS scoring |

**Not copied:** alanine dipeptide, alanine tetrapeptide, AdK, any ala2/ala4 analysis.

**Not copied (still running in `taps-gromacs`):** native `cln025_water` 500 ns cMD (`run_md.py --system cln025_water --length 500`). Copy it after that job finishes.

## Hard budget / protocol (do not change quietly)

- Typical adaptive campaign: **82 ns** (10 ns init + 12 × 6 × 1 ns), same as the existing CLN runs.
- Folded-like: backbone RMSD < **0.25 nm**.
- Committed: consecutive residence ≥ **40 ps**.
- All methods must use the same total budget, force field (AMBER99SB-ILDN + TIP3P), temperature, and randomization protocol.

## Next work (Phase 1 — no new MD, no new DL)

Read existing CLN025 trajectories, score each candidate on Novelty / Boundary / Kinetic proxy / Commitment labels / Uncertainty proxy / Information-gain proxy, then compare LAST, LC, Random, MOAS-static, MOAS-dynamic, and Pareto **offline**. Only start a new GROMACS adaptive campaign if commitment-aware or multi-objective utility clearly beats LAST on committed exploration.

```bash
cd /home/ly/TAPS/moas-gromacs
python3 run_md.py --list
python3 run_md.py --check --system cln025_unfolded
```

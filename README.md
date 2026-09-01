# TAPS / MOAS

Multi-objective adaptive sampling (MOAS) for molecular dynamics, with GROMACS.

This repository holds **code, MDP templates, and method notes**. Production trajectories and checkpoints are not included (they are hundreds of gigabytes locally).

## Layout

| Directory | What it is |
|---|---|
| `moas-gromacs/` | CLN025 mainline: seven methods × 3 seeds, 82 ns, CA-RMSD + Rg, committed fold ≥ 40 ps |
| `moas-adk/` | Apo adenylate kinase: Random / LAST / Least-counts / MOAS-static, 200 ns, LID–CORE and NMP–CORE angles, commit ≥ 200 ps |
| `moas-mbp/` | Apo maltose-binding protein: same four methods, 200 ns, N/C-domain CA-COM distance + hinge angle, commit ≥ 200 ps |
| `taps-gromacs/` | Earlier TAPS / LAST / Hybrid campaigns (CLN025, alanine dipeptide) |
| `paper_outline.md` | Paper outline |

Later systems keep **four methods only**: Random, LAST, Least-counts, MOAS-static. TAPS / dynamic / Pareto stay on CLN025.

Success is a **committed** basin visit, not first-hit.

## Run (after preparing boxes locally)

```bash
# AdK n=1
cd moas-adk
bash scripts/run_gpu_queue.sh

# AdK replicates
SEED=1 bash scripts/run_discover.sh
SEED=2 bash scripts/run_discover.sh

# MBP n=1
cd moas-mbp
bash scripts/run_gpu_queue.sh
```

GROMACS with GPU support and Python 3 (`numpy`) are required. Force field: AMBER99SB-ILDN + TIP3P.

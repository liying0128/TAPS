# TAPS / MOAS

Multi-objective adaptive sampling (MOAS) for molecular dynamics, with GROMACS.

**Data and software (JCTC / JCIM):** see [`SOFTWARE.md`](SOFTWARE.md) and [`paper/protocol/`](paper/protocol/). Ranking, CV windows, and commitment definitions used in the manuscript live there. License: [MIT](LICENSE). GitHub: https://github.com/liying0128/TAPS

This repository holds **code, MDP templates, manuscript drafts, and method notes**. Production trajectories and checkpoints are not included (they are hundreds of gigabytes locally). See `paper/simulation_paths.md` for where those files live on the lab machines.

## Layout

| Directory | What it is |
|---|---|
| `moas-adk/` | Apo adenylate kinase: 200 ns, LID–CORE and NMP–CORE angles, commit ≥ 200 ps |
| `moas-mbp/` | Apo maltose-binding protein: 1 μs, N/C-domain CA-COM distance + hinge angle, commit ≥ 200 ps |
| `taps-gromacs/` | CLN025 folding (82 ns, Cα-RMSD + Rg, commit ≥ 40 ps) and earlier TAPS / LAST campaigns |
| `moas-knn/` | kNN-AS (Rovers et al., JCTC 2025) runner and lab-machine queues |
| `moas-gromacs/` | Earlier CLN025 seven-method campaigns |
| `paper/` | Manuscript / SI drafts, figures, and n = 3 + ablation metric tables |
| `paper_outline.md` | Paper outline |

Main-text methods (n = 3): **Random, LAST, Least-counts, kNN-AS, MOAS**. TAPS is a CLN025 supplementary comparison only. Ablation of novelty / boundary / target combinations is n = 1 on AdK and MBP.

Success is a **committed** basin visit and target-basin occupancy, not first-hit.

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

# kNN-AS only (same CVs / budget as the other methods)
bash moas-adk/scripts/run_knn.sh
bash moas-mbp/scripts/run_knn.sh
bash taps-gromacs/scripts/run_knn.sh
```

GROMACS with GPU support and Python 3 (`numpy`) are required. Force field: AMBER99SB-ILDN + TIP3P.

Rebuild figures and Word drafts from finished `history.json` files:

```bash
python3 paper/make_figures.py
python3 paper/build_docx.py
```

# Protocol deposit (JCTC / JCIM)

This folder is the reviewer-facing copy of **ranking**, **CV windows**, and **commitment** used in the manuscript. It does not run MD. Production adaptive loops remain in `moas-adk/`, `moas-mbp/`, and `taps-gromacs/`.

Repository: https://github.com/liying0128/TAPS

## Files

| File | Manuscript role |
|---|---|
| `windows.json` | Target window W, τ, CVs, budgets for CLN025 / AdK / MBP |
| `adk_angle_refs.json` | Production AdK LID/NMP thresholds and CA groups |
| `mbp_cv_refs.json` | Production MBP distance/hinge thresholds and CA groups |
| `ranking.py` | Novelty, LAST frontier, target proximity, equal-percentile mix, diversity greedy |
| `commitment.py` | First committed visit, occupancy, residence times |
| `knn_as.py` | kNN-AS score (Rovers et al., JCTC 2025); k = 5, P = 0.5 |

## How to score one round (no MD)

```python
from ranking import novelty_scores, last_frontier_scores, target_scores_adk, moas_mix, greedy_diverse
# x_all, y_all: visited pool CVs
# x_q, y_q: candidate window endpoints
nov = novelty_scores(x_all, y_all, x_q, y_q)
bnd = last_frontier_scores(x_all, y_all, x_q, y_q)
tgt = target_scores_adk(x_q, y_q, refs)
score = moas_mix(nov, bnd, tgt, method="moas")   # equal percentile ranks
seeds = greedy_diverse(x_q, y_q, score, n_seeds=6, min_sep=1.0)
```

Ablation methods `nov`, `bnd`, `tgt`, `novbnd`, `novtgt`, `bndtgt` zero unused ranks and renormalize (`MOAS_OBJECTIVE_WEIGHTS`).

## Figures and tables

Rebuild from campaign `history.json` / `cvs.npz` (not in git; too large):

```bash
python3 paper/make_figures.py
python3 paper/build_docx.py
```

Numerical values already in the paper are in `paper/tables/*.csv` (machine-readable).

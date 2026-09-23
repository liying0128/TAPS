# Data and software availability

This repository is the public deposit for the MOAS manuscript, prepared to meet:

- **JCTC and JCIM joint editorial** (J. Chem. Theory Comput. 2026, 22, 4199–4200; effective 1 May 2026): Data and Software Availability Statement at submission; custom code, inputs, CV/system definitions, and key numerical data in a public repository.
- **JCIM method/data sharing editorial** (J. Chem. Inf. Model. 2020, 60, 5868–5869; 10.1021/acs.jcim.0c01389): novel methods with source code on GitHub under an open license; machine-readable data; a **Data and Software Availability** section in the manuscript.
- **ACS Research Data Policy Level 2** (both journals): a Data Availability Statement at submission.

Repository: https://github.com/liying0128/TAPS  
License: MIT (`LICENSE`).

## What is in git (enough to reproduce the method and the tables)

| Item | Location |
|---|---|
| Ranking (novelty, LAST, target, equal-percentile mix, diversity, ablation weights) | `paper/protocol/ranking.py` and production loops below |
| kNN-AS scorer (k = 5, P = 0.5) | `paper/protocol/knn_as.py`, `moas-adk/knn_as.py` |
| Commitment, occupancy, residence times | `paper/protocol/commitment.py` |
| CV windows and τ | `paper/protocol/windows.json` |
| AdK LID/NMP groups and thresholds | `paper/protocol/adk_angle_refs.json`, `moas-adk/systems/adk/angle_refs.json`, `moas-adk/adk_angles.py` |
| MBP domain/hinge groups and thresholds | `paper/protocol/mbp_cv_refs.json`, `moas-mbp/systems/mbp/cv_refs.json`, `moas-mbp/mbp_cvs.py` |
| Production adaptive loops | `taps-gromacs/stage13_cln025_discover.py`, `moas-adk/stage_adk_discover.py`, `moas-mbp/stage_mbp_discover.py` |
| MDP templates | `moas-adk/shared/mdp/`, `moas-mbp/shared/mdp/`, `taps-gromacs/` MDP files that remain in tree |
| Figure/table builder | `paper/make_figures.py`, `paper/build_docx.py` |
| Key numerical data (n = 3, ablation, bootstrap, τ-robustness, residence, windows) | `paper/tables/*.csv` |

## What is not in git

Full GROMACS trajectories, checkpoints, and per-frame `cvs.npz` are hundreds of gigabytes (`*.xtc`, `*.tpr`, `analysis/` are gitignored). They are available from the corresponding author on request. Campaign tags are listed in Supporting Information section S11.

## Software versions used for production MD

- GROMACS 2024.3 (GPU builds on the lab machines) and GROMACS 2025.1 on the writing workstation
- Force field AMBER99SB-ILDN, water TIP3P
- Python 3 with NumPy (ranking / CVs) and Matplotlib / python-docx (figures and Word drafts)
- See `requirements.txt` for the analysis stack

## Suggested Data and Software Availability statement (manuscript)

The data underlying this study are available in the published article, the Supporting Information, and at https://github.com/liying0128/TAPS. Ranking code, CV definitions, and commitment/occupancy functions are in `paper/protocol/`. Numerical tables underlying the figures are in `paper/tables/`. Full MD trajectories are available from the corresponding author upon request.

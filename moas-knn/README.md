# kNN-AS on the existing CLN025 → AdK → MBP campaigns

Fifth method only: **kNN-AS** (Rovers et al., *J. Chem. Theory Comput.* 2025, [10.1021/acs.jctc.5c00462](https://doi.org/10.1021/acs.jctc.5c00462)).  
Same CVs, commit protocol, init, short-MD length, and budget as Random / LAST / Least-counts / MOAS-static. Not mixed into those four-method queues.

Score: subsample the visited 2-D CV cloud (P=0.5, k=5), then `||Σ (z_j − q)||` over k nearest neighbors of each candidate window. No target state. Intended as a LAST-like frontier baseline.

| | CLN025 | AdK | MBP |
|---|---|---|---|
| start | unfolded | open apo | open apo |
| init | 10 ns | 20 ns | 20 ns |
| shorts | 1 ns × 6 × 12 | 2 ns × 6 × 15 | 2 ns × 6 × 82 |
| budget | 82 ns | 200 ns | 1000 ns |
| tag (seed=0) | `discover_knn` | `adk_knn` | `mbp_knn` |

173 (Quadro P2200, 4 CPU threads): files are prepared under `/home/ly/TAPS`. GPU job is **not** started by the copy.

```bash
# on 173, tmux session moas-mbp (do not kill-session)
source /home/ly/TAPS/moas-knn/env_remote.sh
python3 /home/ly/TAPS/taps-gromacs/stage13_cln025_discover.py --check --methods knn
python3 /home/ly/TAPS/moas-adk/stage_adk_discover.py --check --methods knn
python3 /home/ly/TAPS/moas-mbp/stage_mbp_discover.py --check --methods knn

NT=4 SEED=0 bash /home/ly/TAPS/moas-knn/run_173.sh
```

Single system:

```bash
NT=4 SEED=0 bash /home/ly/TAPS/taps-gromacs/scripts/run_knn.sh
NT=4 SEED=0 bash /home/ly/TAPS/moas-adk/scripts/run_knn.sh
NT=4 SEED=0 bash /home/ly/TAPS/moas-mbp/scripts/run_knn.sh
```

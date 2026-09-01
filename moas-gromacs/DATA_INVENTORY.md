Copied from taps-gromacs on 2026-08-25 for MOAS / CLN025 only.

systems/chignolin_cln025/
  structures/                 native, NMR, unfolded PDBs
  gmx_common/                 pdb2gmx protein.gro + topol (native)
  gmx_common_unfolded/
  water/                      native start: EM/NVT/NPT + cMD 100 ns, 200 ns
  water_unfolded/             unfolded start: EM/NVT/NPT + cMD 100 ns, 500 ns
  water_unfolded/adaptive/campaigns/
    discover_{taps,last,lc}          original 82 ns
    discover_s1_*  discover_s2_*     two extra first-hit replicates
    hybrid1_25, hybrid2_50, hybrid3_75, hybrid_cov and listed _s1/_s2

data/legacy/cln025_unfolded/  RMSD/Rg, history.json, firsthit_reps_report.txt
data/legacy/hybrid_offline/   cln_* FEU / complement / uncertainty / novelty
data/candidates/              cln_candidates.npz + meta/report

Hard-linked (same inode as taps-gromacs, does not double disk):
  *.xtc and most binary MD/analysis files

Real copies (safe to edit here):
  *.mdp *.top *.itp Python/YAML/README

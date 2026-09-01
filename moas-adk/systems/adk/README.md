# Apo AdK (E. coli)

- Open: PDB 4AKE chain A
- Closed: PDB 1AKE chain A, AP5A ligand removed

Production starts from **open**. Closed is used only for LID/NMP angle references.

Solvation: 1.2 nm cubic buffer, TIP3P, 0.15 M NaCl, AMBER99SB-ILDN.

```bash
bash scripts/prepare_adk.sh
bash scripts/run_em_eq.sh
```

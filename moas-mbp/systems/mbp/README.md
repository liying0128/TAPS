# Apo MBP (E. coli maltose-binding protein)

- Open: PDB 1OMP chain A
- Closed: PDB 1ANF chain A, maltose removed

Production starts from **open**. Closed is used only for domain-distance / hinge-angle references.

Solvation: 1.2 nm dodecahedron buffer, TIP3P, 0.15 M NaCl, AMBER99SB-ILDN.

```bash
bash scripts/prepare_mbp.sh
bash scripts/run_em_eq.sh
```

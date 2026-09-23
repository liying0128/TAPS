# Draft numbers for Results

## CLN025
- Random: hit 2/3, commit 0/3, occupancy 0.01% (IQR 0.00–0.01), median commit n.d. ns; KM median n.r. ns (boot 95% n.r.–n.r.); P(commit) 0.00 [0.00, 0.00]; occ 0.01% [0.00, 0.01]
- LAST: hit 3/3, commit 3/3, occupancy 1.66% (IQR 1.02–2.07), median commit 46.4 ns; KM median 46.4 ns (boot 95% 46.178–80.494); P(commit) 1.00 [1.00, 1.00]; occ 1.66% [0.38, 2.48]
- Least-counts: hit 3/3, commit 3/3, occupancy 0.42% (IQR 0.32–0.62), median commit 68.6 ns; KM median 68.6 ns (boot 95% 34.124–80.266); P(commit) 1.00 [1.00, 1.00]; occ 0.42% [0.22, 0.83]
- kNN-AS: hit 3/3, commit 1/3, occupancy 0.14% (IQR 0.07–0.33), median commit 56.6 ns; KM median n.r. ns (boot 95% 56.648–56.648); P(commit) 0.33 [0.00, 1.00]; occ 0.14% [0.00, 0.52]
- MOAS: hit 3/3, commit 3/3, occupancy 5.25% (IQR 4.65–6.02), median commit 36.1 ns; KM median 36.1 ns (boot 95% 34.086–40.12); P(commit) 1.00 [1.00, 1.00]; occ 5.25% [4.05, 6.79]
- TAPS: hit 3/3, commit 1/3, occupancy 0.24% (IQR 0.16–0.46), median commit 80.2 ns

## AdK
- Random: hit 1/3, commit 0/3, occupancy 0.00% (IQR 0.00–0.07), median commit n.d. ns; KM median n.r. ns (boot 95% n.r.–n.r.); P(commit) 0.00 [0.00, 0.00]; occ 0.00% [0.00, 0.14]
- LAST: hit 1/3, commit 0/3, occupancy 0.00% (IQR 0.00–0.02), median commit n.d. ns; KM median n.r. ns (boot 95% n.r.–n.r.); P(commit) 0.00 [0.00, 0.00]; occ 0.00% [0.00, 0.03]
- Least-counts: hit 3/3, commit 2/3, occupancy 0.48% (IQR 0.26–1.01), median commit 191.4 ns; KM median 192.5 ns (boot 95% 190.352–192.518); P(commit) 0.67 [0.00, 1.00]; occ 0.48% [0.03, 1.53]
- kNN-AS: hit 1/3, commit 1/3, occupancy 0.00% (IQR 0.00–3.66), median commit 96.1 ns; KM median n.r. ns (boot 95% 96.086–96.086); P(commit) 0.33 [0.00, 1.00]; occ 0.00% [0.00, 7.31]
- MOAS: hit 3/3, commit 3/3, occupancy 14.85% (IQR 7.78–21.34), median commit 105.7 ns; KM median 105.7 ns (boot 95% 103.444–192.272); P(commit) 1.00 [1.00, 1.00]; occ 14.85% [0.72, 27.83]

## MBP
- Random: hit 1/3, commit 0/3, occupancy 0.00% (IQR 0.00–0.00), median commit n.d. ns; KM median n.r. ns (boot 95% n.r.–n.r.); P(commit) 0.00 [0.00, 0.00]; occ 0.00% [0.00, 0.01]
- LAST: hit 2/3, commit 1/3, occupancy 0.02% (IQR 0.01–13.01), median commit 320.4 ns; KM median n.r. ns (boot 95% 320.416–320.416); P(commit) 0.33 [0.00, 1.00]; occ 0.02% [0.00, 26.01]
- Least-counts: hit 3/3, commit 1/3, occupancy 0.03% (IQR 0.02–0.32), median commit 414.0 ns; KM median n.r. ns (boot 95% 414.008–414.008); P(commit) 0.33 [0.00, 1.00]; occ 0.03% [0.01, 0.60]
- kNN-AS: hit 3/3, commit 2/3, occupancy 0.14% (IQR 0.07–0.45), median commit 704.7 ns; KM median 836.8 ns (boot 95% 572.596–836.83); P(commit) 0.67 [0.00, 1.00]; occ 0.14% [0.00, 0.76]
- MOAS: hit 3/3, commit 3/3, occupancy 37.15% (IQR 32.78–39.63), median commit 442.8 ns; KM median 442.8 ns (boot 95% 216.76–503.544); P(commit) 1.00 [1.00, 1.00]; occ 37.15% [28.40, 42.12]

## Commitment-threshold robustness (existing cvs.npz; no new MD)
Production τ: CLN025 40 ps (time sojourn); AdK/MBP 200 ps (consecutive frames, Δt = 2 ps).

CLN025 τ = 20/40/60/80 ps, commit n/3: Random 0/0/0/0; LAST 3/3/2/2; Least-counts 3/3/1/1; kNN-AS 2/1/0/0; MOAS 3/3/3/3; TAPS 3/1/1/1. MOAS occupancy 5.25% (τ-invariant).
AdK τ = 100/200/300/500 ps, commit n/3: Random 1/0/0/0; LAST 0/0/0/0; Least-counts 2/2/2/1; kNN-AS 1/1/1/1; MOAS 3/3/3/2. MOAS occupancy 14.85% (τ-invariant).
MBP τ = 100/200/300/500 ps, commit n/3: Random 1/0/0/0; LAST 2/1/1/1; Least-counts 1/1/1/1; kNN-AS 2/2/2/1; MOAS 3/3/3/3. MOAS occupancy 37.15% (τ-invariant).

## Residence times and neighboring windows (existing cvs.npz; no new MD)
Median longest sojourn (ps): CLN Random 2, LAST 152, LC 46, kNN 20, MOAS 342, TAPS 34; AdK Random/LAST/kNN 0, LC 330, MOAS 1820; MBP Random 0, LAST 120, LC 70, kNN 330, MOAS 36470.
Typical sojourn median 2–20 ps for every method; the distinction is the tail. Replicate-averaged P(T≥τ): CLN MOAS 0.097 vs LAST 0.036; AdK MOAS 0.060 vs kNN 0.022; MBP MOAS 0.087 vs LAST 0.040.
Window occupancy: MOAS highest at production W and every looser or moderately tighter populated cutoff (CLN RMSD 0.20–0.40 nm; AdK Δ≥0; MBP all expansions, including tighter −2 with MOAS 17% vs others ≤0.02%).


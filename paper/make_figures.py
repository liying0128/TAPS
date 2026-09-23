#!/usr/bin/env python3
"""Draft main-text figures from finished MOAS campaigns.

Does not run MD. Incomplete ablation bars are hatched if round < budget.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Polygon, Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "figures"
TAB = Path(__file__).resolve().parent / "tables"
REMOTE = Path(__file__).resolve().parent / "data" / "hist_55"

CLN_CAMP = ROOT / "taps-gromacs/analysis/cln025_unfolded/campaigns"
ADK_CAMP = ROOT / "moas-adk/analysis/adk_open/campaigns"
MBP_CAMP = ROOT / "moas-mbp/analysis/mbp_open/campaigns"

FOLD_RMSD = 0.25
CLN_COMMIT_PS = 40.0
BUDGET = {"CLN025": 82.154, "AdK": 200.19, "MBP": 1004.99}

METHODS = ["Random", "LAST", "Least-counts", "kNN-AS", "MOAS"]
MC = {
    "Random": "#6B6B6B",
    "LAST": "#2B6CB0",
    "Least-counts": "#2F855A",
    "kNN-AS": "#DD6B20",
    "MOAS": "#C53030",
    "TAPS": "#6B46C1",
}
AB_ORDER = ["nov", "bnd", "tgt", "novbnd", "novtgt", "bndtgt", "moas"]
AB_LABEL = {
    "nov": "Novelty",
    "bnd": "Boundary",
    "tgt": "Target",
    "novbnd": "Nov+Bnd",
    "novtgt": "Nov+Tgt",
    "bndtgt": "Bnd+Tgt",
    "moas": "Full MOAS",
}
AB_COLOR = {
    "nov": "#63B3ED",
    "bnd": "#3182CE",
    "tgt": "#ED8936",
    "novbnd": "#38B2AC",
    "novtgt": "#DD6B20",
    "bndtgt": "#D69E2E",
    "moas": "#C53030",
}
AB_SHORT = {
    "nov": "N",
    "bnd": "B",
    "tgt": "T",
    "novbnd": "NB",
    "novtgt": "NT",
    "bndtgt": "BT",
    "moas": "M",
}
AB_WEIGHTS = {
    "nov": (1.0, 0.0, 0.0),
    "bnd": (0.0, 1.0, 0.0),
    "tgt": (0.0, 0.0, 1.0),
    "novbnd": (1.0, 1.0, 0.0),
    "novtgt": (1.0, 0.0, 1.0),
    "bndtgt": (0.0, 1.0, 1.0),
    "moas": (1.0, 1.0, 1.0),
}
AB_LS = {
    "nov": "--",
    "bnd": "--",
    "tgt": "--",
    "novbnd": "-.",
    "novtgt": "-.",
    "bndtgt": "-.",
    "moas": "-",
}

# (system, method, rep) -> (kind, tag)  kind in {cln, adk, mbp}
N3 = {
    ("CLN025", "Random", 0): ("cln", "moas_random"),
    ("CLN025", "Random", 1): ("cln", "moas_s1_random"),
    ("CLN025", "Random", 2): ("cln", "moas_s2_random"),
    ("CLN025", "LAST", 0): ("cln", "discover_last"),
    ("CLN025", "LAST", 1): ("cln", "discover_s1_last"),
    ("CLN025", "LAST", 2): ("cln", "discover_s2_last"),
    ("CLN025", "Least-counts", 0): ("cln", "discover_lc"),
    ("CLN025", "Least-counts", 1): ("cln", "discover_s1_lc"),
    ("CLN025", "Least-counts", 2): ("cln", "discover_s2_lc"),
    ("CLN025", "kNN-AS", 0): ("cln", "discover_knn"),
    ("CLN025", "kNN-AS", 1): ("cln", "discover_s1_knn"),
    ("CLN025", "kNN-AS", 2): ("cln", "discover_s2_knn"),
    ("CLN025", "MOAS", 0): ("cln", "moas_static"),
    ("CLN025", "MOAS", 1): ("cln", "moas_s1_static"),
    ("CLN025", "MOAS", 2): ("cln", "moas_s2_static"),
    ("CLN025", "TAPS", 0): ("cln", "discover_taps"),
    ("CLN025", "TAPS", 1): ("cln", "discover_s1_taps"),
    ("CLN025", "TAPS", 2): ("cln", "discover_s2_taps"),
    ("AdK", "Random", 0): ("adk", "adk_random"),
    ("AdK", "Random", 1): ("adk", "adk_s1_random"),
    ("AdK", "Random", 2): ("adk", "adk_s2_random"),
    ("AdK", "LAST", 0): ("adk", "adk_last"),
    ("AdK", "LAST", 1): ("adk", "adk_s1_last"),
    ("AdK", "LAST", 2): ("adk", "adk_s2_last"),
    ("AdK", "Least-counts", 0): ("adk", "adk_lc"),
    ("AdK", "Least-counts", 1): ("adk", "adk_s1_lc"),
    ("AdK", "Least-counts", 2): ("adk", "adk_s2_lc"),
    ("AdK", "kNN-AS", 0): ("adk", "adk_knn"),
    ("AdK", "kNN-AS", 1): ("adk", "adk_s1_knn"),
    ("AdK", "kNN-AS", 2): ("adk", "adk_s2_knn"),
    ("AdK", "MOAS", 0): ("adk", "adk_static"),
    ("AdK", "MOAS", 1): ("adk", "adk_s1_static"),
    ("AdK", "MOAS", 2): ("adk", "adk_s2_static"),
    ("MBP", "Random", 0): ("mbp", "mbp_random"),
    ("MBP", "Random", 1): ("mbp", "mbp_s1_random"),
    ("MBP", "Random", 2): ("mbp", "mbp_s2_random"),
    ("MBP", "LAST", 0): ("mbp", "mbp_last"),
    ("MBP", "LAST", 1): ("mbp", "mbp_s1_last"),
    ("MBP", "LAST", 2): ("mbp", "mbp_s2_last"),
    ("MBP", "Least-counts", 0): ("mbp", "mbp_lc"),
    ("MBP", "Least-counts", 1): ("mbp", "mbp_s1_lc"),
    ("MBP", "Least-counts", 2): ("mbp", "mbp_s2_lc"),
    ("MBP", "kNN-AS", 0): ("mbp", "mbp_knn"),
    ("MBP", "kNN-AS", 1): ("mbp", "mbp_s1_knn"),
    ("MBP", "kNN-AS", 2): ("mbp", "mbp_s2_knn"),
    ("MBP", "MOAS", 0): ("mbp", "mbp_static"),
    ("MBP", "MOAS", 1): ("mbp", "mbp_s1_static"),
    ("MBP", "MOAS", 2): ("mbp", "mbp_s2_static"),
}

ADK_ABLATION = {
    "nov": "adk_nov",
    "bnd": "adk_bnd",
    "tgt": "adk_tgt",
    "novbnd": "adk_novbnd",
    "novtgt": "adk_novtgt",
    "bndtgt": "adk_bndtgt",
    "moas": "adk_static",
}
MBP_ABLATION = {
    "nov": "mbp_nov",
    "bnd": "mbp_bnd",
    "tgt": "mbp_tgt",
    "novbnd": "mbp_novbnd",
    "novtgt": "mbp_novtgt",
    "bndtgt": "mbp_bndtgt",
    "moas": "mbp_static",
}


def style():
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 10,
            "axes.titlesize": 10,
            "axes.linewidth": 0.8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.dpi": 220,
            "figure.dpi": 140,
            "axes.spines.top": True,
            "axes.spines.right": True,
        }
    )


def last_round(path: Path) -> dict:
    h = json.loads(path.read_text())
    return h[-1] if isinstance(h, list) else (h.get("rounds") or [h])[-1]


def first_commit_from_mask(mask: np.ndarray, t_ps: np.ndarray, commit_ps: float):
    t = np.asarray(t_ps, dtype=np.float64)
    m = np.asarray(mask, dtype=bool)
    n = len(m)
    i = 0
    while i < n:
        if not m[i]:
            i += 1
            continue
        j = i + 1
        while j < n and m[j]:
            j += 1
        dt_end = float(t[1] - t[0]) if n > 1 else 2.0
        if j < n:
            dt_end = float(t[j] - t[j - 1])
        elif n > 1:
            dt_end = float(np.median(np.diff(t)))
        dur = float(t[j - 1] - t[i]) + dt_end
        if dur >= commit_ps:
            return float(t[i]) / 1000.0
        i = j
    return None


def first_commit_nframes(mask: np.ndarray, t_ps: np.ndarray, commit_ps: float):
    """AdK/MBP production definition: consecutive True frames >= round(τ / Δt)."""
    t = np.asarray(t_ps, dtype=np.float64)
    m = np.asarray(mask, dtype=bool)
    n = len(m)
    if n == 0:
        return None
    dt = float(t[1] - t[0]) if n > 1 else 2.0
    need = max(1, int(round(commit_ps / max(dt, 1e-9))))
    padded = np.concatenate([[False], m, [False]])
    d = np.diff(padded.astype(np.int8))
    i0 = np.flatnonzero(d == 1)
    i1 = np.flatnonzero(d == -1)
    ok = np.flatnonzero((i1 - i0) >= need)
    if len(ok) == 0:
        return None
    return float(t[i0[ok[0]]]) / 1000.0


def commit_time_at(kind: str, mask: np.ndarray, t_ps: np.ndarray, commit_ps: float):
    if kind == "cln":
        return first_commit_from_mask(mask, t_ps, commit_ps)
    return first_commit_nframes(mask, t_ps, commit_ps)


def load_campaign_z(kind: str, tag: str):
    paths = []
    d = campaign_dir(kind, tag)
    if d is not None:
        paths.append(d / "cvs.npz")
    paths.append(REMOTE / kind / tag / "cvs.npz")
    seen: set[Path] = set()
    for p in paths:
        if not p.exists():
            continue
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        return np.load(p)
    return None


def load_window_mask(kind: str, tag: str):
    z = load_campaign_z(kind, tag)
    if z is None:
        return None, None
    t = np.asarray(z["t_ps"], dtype=np.float64)
    if kind == "cln":
        return t, np.asarray(z["rmsd"], dtype=np.float64) < FOLD_RMSD
    return t, np.asarray(z["closed"], dtype=bool)


def sojourns_ps(kind: str, mask: np.ndarray, t_ps: np.ndarray) -> np.ndarray:
    """Contiguous residence times (ps) using the production sojourn definition."""
    t = np.asarray(t_ps, dtype=np.float64)
    m = np.asarray(mask, dtype=bool)
    n = len(m)
    if n == 0:
        return np.asarray([], dtype=float)
    padded = np.concatenate([[False], m, [False]])
    d = np.diff(padded.astype(np.int8))
    i0 = np.flatnonzero(d == 1)
    i1 = np.flatnonzero(d == -1)
    if kind == "cln":
        med_dt = float(np.median(np.diff(t))) if n > 1 else 2.0
        durs = []
        for a, b in zip(i0, i1):
            dt_end = float(t[b] - t[b - 1]) if b < n else med_dt
            durs.append(float(t[b - 1] - t[a]) + dt_end)
        return np.asarray(durs, dtype=float)
    dt = float(t[1] - t[0]) if n > 1 else 2.0
    return np.asarray([(b - a) * dt for a, b in zip(i0, i1)], dtype=float)


CLN_RMSD_GRID = [0.15, 0.20, 0.25, 0.30, 0.40]
ADK_MARGIN_DEG = [-8.0, -4.0, 0.0, 4.0, 8.0]
MBP_WINDOW_EXPAND = [(-0.06, -6.0), (-0.03, -3.0), (0.0, 0.0), (0.03, 3.0), (0.06, 6.0)]


COMMIT_TAUS = {
    "CLN025": [20.0, 40.0, 60.0, 80.0],
    "AdK": [100.0, 200.0, 300.0, 500.0],
    "MBP": [100.0, 200.0, 300.0, 500.0],
}
PROD_TAU = {"CLN025": 40.0, "AdK": 200.0, "MBP": 200.0}


def campaign_dir(kind: str, tag: str) -> Path | None:
    if kind == "cln":
        local = CLN_CAMP / tag
        remote = REMOTE / "cln" / tag
        for p in (local, remote):
            if (p / "history.json").exists():
                return p
        return None
    if kind == "adk":
        for p in (ADK_CAMP / tag, REMOTE / "adk" / tag):
            if (p / "history.json").exists():
                return p
        return None
    for p in (MBP_CAMP / tag, REMOTE / "mbp" / tag):
        if (p / "history.json").exists():
            return p
    return None


def load_metrics(kind: str, tag: str) -> dict | None:
    d = campaign_dir(kind, tag)
    if d is None:
        return None
    r = last_round(d / "history.json")
    out = {
        "tag": tag,
        "kind": kind,
        "path": str(d),
        "sim_ns": r.get("sim_ns"),
        "coverage": r.get("coverage"),
        "round": r.get("round"),
        "complete": True,
    }
    if kind == "cln":
        out["hit"] = r.get("first_fold_ns")
        out["occ"] = r.get("frac_fold")
        cvs = d / "cvs.npz"
        if cvs.exists():
            z = np.load(cvs)
            mask = z["rmsd"] < FOLD_RMSD
            out["hit"] = None if not mask.any() else float(z["t_ps"][np.flatnonzero(mask)[0]]) / 1000.0
            out["commit"] = first_commit_from_mask(mask, z["t_ps"], CLN_COMMIT_PS)
            out["occ"] = float(mask.mean())
        else:
            out["commit"] = None
            if (out["occ"] or 0) > 0 and out["hit"] is None:
                pass
    else:
        out["hit"] = r.get("first_hit_ns")
        out["commit"] = r.get("first_commit_ns")
        out["occ"] = r.get("frac_closed")
        # running campaign: fewer rounds than budget
        if kind == "mbp" and (r.get("round") or 0) < 82:
            out["complete"] = False
        if kind == "adk" and (r.get("round") or 0) < 15:
            out["complete"] = False
    return out


def load_history(kind: str, tag: str) -> list[dict] | None:
    d = campaign_dir(kind, tag)
    if d is None:
        return None
    h = json.loads((d / "history.json").read_text())
    return h if isinstance(h, list) else (h.get("rounds") or [h])


def ablation_record(kind: str, tag: str) -> dict | None:
    """Ablation metrics plus occupancy trajectory, hit→commit lag, and post-commit occupancy."""
    m = load_metrics(kind, tag)
    if m is None:
        return None
    h = load_history(kind, tag) or []
    m["traj"] = [
        (float(r["sim_ns"]), float(r.get("frac_closed") or 0.0), float(r.get("coverage") or 0.0)) for r in h
    ]
    m["lag"] = None if m["hit"] is None or m["commit"] is None else float(m["commit"]) - float(m["hit"])
    m["post_occ"] = None
    d = campaign_dir(kind, tag)
    cvs = None if d is None else d / "cvs.npz"
    if cvs is not None and cvs.exists() and m["commit"] is not None:
        z = np.load(cvs)
        t = np.asarray(z["t_ps"], dtype=np.float64) / 1000.0
        closed = np.asarray(z["closed"], dtype=np.float64)
        sel = t >= float(m["commit"])
        if sel.any():
            m["post_occ"] = float(closed[sel].mean())
    m["late_occ"] = m.get("occ")
    if len(h) >= 2:
        t_end = float(h[-1]["sim_ns"])
        t_cut = 0.75 * t_end
        prev = h[0]
        for r in h:
            if float(r["sim_ns"]) <= t_cut:
                prev = r
            else:
                break
        t0, f0 = float(prev["sim_ns"]), float(prev.get("frac_closed") or 0.0)
        t1, f1 = t_end, float(h[-1].get("frac_closed") or 0.0)
        m["late_occ"] = (f1 * t1 - f0 * t0) / max(t1 - t0, 1e-9)
    return m


def _barycentric(nov: float, bnd: float, tgt: float):
    s = nov + bnd + tgt
    nov, bnd, tgt = nov / s, bnd / s, tgt / s
    return tgt + 0.5 * nov, (np.sqrt(3.0) / 2.0) * nov


def collect_n3() -> list[dict]:
    rows = []
    for (sys, method, rep), (kind, tag) in N3.items():
        m = load_metrics(kind, tag)
        if m is None:
            rows.append(
                {
                    "system": sys,
                    "method": method,
                    "rep": rep,
                    "tag": tag,
                    "hit": None,
                    "commit": None,
                    "occ": None,
                    "coverage": None,
                    "sim_ns": None,
                    "missing": True,
                    "complete": False,
                }
            )
            continue
        rows.append(
            {
                "system": sys,
                "method": method,
                "rep": rep,
                "tag": tag,
                "hit": m["hit"],
                "commit": m["commit"],
                "occ": m["occ"],
                "coverage": m["coverage"],
                "sim_ns": m["sim_ns"],
                "missing": False,
                "complete": m["complete"],
            }
        )
    return rows


N_BOOT = 10000
BOOT_SEED = 20260923
KM_METHODS = ["Random", "LAST", "Least-counts", "kNN-AS", "MOAS"]


def collect_threshold_robustness() -> list[dict]:
    recs = []
    for (sys, method, rep), (kind, tag) in N3.items():
        t, mask = load_window_mask(kind, tag)
        occ = None if mask is None else float(np.mean(mask))
        for tau in COMMIT_TAUS[sys]:
            cns = None if mask is None else commit_time_at(kind, mask, t, tau)
            recs.append(
                {
                    "system": sys,
                    "method": method,
                    "rep": rep,
                    "tag": tag,
                    "tau_ps": tau,
                    "commit_ns": cns,
                    "occupancy": occ,
                    "committed": cns is not None,
                }
            )
    return recs


def _tau_methods(sys: str) -> list[str]:
    return METHODS + (["TAPS"] if sys == "CLN025" else [])


def fig_commit_threshold(recs: list[dict]):
    fig, axes = plt.subplots(3, 3, figsize=(10.8, 9.2))
    fig.subplots_adjust(hspace=0.42, wspace=0.30)
    systems = ["CLN025", "AdK", "MBP"]
    letters = ["ABC", "DEF", "GHI"]
    for j, sys in enumerate(systems):
        taus = np.asarray(COMMIT_TAUS[sys], dtype=float)
        methods = _tau_methods(sys)
        ax = axes[0, j]
        panel(ax, letters[0][j])
        ax.set_title(sys)
        ax.axvline(PROD_TAU[sys], color="#A0AEC0", ls=":", lw=1.05, zorder=1)
        for m in methods:
            ys = []
            for tau in taus:
                sub = [r for r in recs if r["system"] == sys and r["method"] == m and abs(r["tau_ps"] - tau) < 1e-9]
                ys.append(sum(bool(r["committed"]) for r in sub) / max(len(sub), 1))
            ax.plot(
                taus,
                ys,
                color=MC[m],
                lw=2.25 if m == "MOAS" else 1.35,
                ls="--" if m == "TAPS" else "-",
                marker="^" if m == "TAPS" else "o",
                ms=5.5,
                label=m,
                zorder=4 if m == "MOAS" else 3,
            )
        ax.set_ylim(-0.08, 1.12)
        ax.set_yticks([0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0], ["0", "1/3", "2/3", "1"])
        ax.set_xticks(taus)
        if j == 0:
            ax.set_ylabel("committed fraction")
            ax.legend(frameon=False, loc="center left", fontsize=6.5)
        ax.set_xlabel("commitment threshold (ps)")

        ax = axes[1, j]
        panel(ax, letters[1][j])
        ax.axvline(PROD_TAU[sys], color="#A0AEC0", ls=":", lw=1.05, zorder=1)
        for m in methods:
            xs, ys = [], []
            for tau in taus:
                sub = [
                    r
                    for r in recs
                    if r["system"] == sys
                    and r["method"] == m
                    and abs(r["tau_ps"] - tau) < 1e-9
                    and r["commit_ns"] is not None
                ]
                if not sub:
                    continue
                xs.append(tau)
                ys.append(float(np.median([r["commit_ns"] for r in sub])))
            if xs:
                ax.plot(
                    xs,
                    ys,
                    color=MC[m],
                    lw=2.25 if m == "MOAS" else 1.35,
                    ls="--" if m == "TAPS" else "-",
                    marker="^" if m == "TAPS" else "o",
                    ms=5.5,
                    zorder=4 if m == "MOAS" else 3,
                )
        ax.set_yscale("log")
        ax.set_xticks(taus)
        ax.set_xlabel("commitment threshold (ps)")
        if j == 0:
            ax.set_ylabel("median time to commit (ns)")

        ax = axes[2, j]
        panel(ax, letters[2][j])
        ax.axvline(PROD_TAU[sys], color="#A0AEC0", ls=":", lw=1.05, zorder=1)
        for m in methods:
            sub0 = [r for r in recs if r["system"] == sys and r["method"] == m]
            occ = [100.0 * (r["occupancy"] or 0.0) for r in sub0 if r["occupancy"] is not None]
            if not occ:
                continue
            y = max(float(np.median(occ)), 1e-3)
            ax.plot(
                taus,
                np.full_like(taus, y),
                color=MC[m],
                lw=2.25 if m == "MOAS" else 1.35,
                ls="--" if m == "TAPS" else "-",
                marker="^" if m == "TAPS" else "o",
                ms=5.5,
                zorder=4 if m == "MOAS" else 3,
            )
        ax.set_yscale("log")
        ax.set_ylim(8e-4, 80)
        ax.set_xticks(taus)
        ax.set_xlabel("commitment threshold (ps)")
        if j == 0:
            ax.set_ylabel("median occupancy (%)")
    save(fig, "figS1_commit_threshold")


def write_threshold_tables(recs: list[dict]):
    TAB.mkdir(parents=True, exist_ok=True)
    dest = TAB / "commit_threshold_robustness.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["system", "method", "rep", "tag", "tau_ps", "commit_ns", "occupancy", "committed"],
        )
        w.writeheader()
        for r in recs:
            w.writerow(r)
    dest2 = TAB / "commit_threshold_summary.csv"
    with dest2.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "system",
                "method",
                "tau_ps",
                "n_commit",
                "n",
                "p_commit",
                "median_ttc",
                "median_occupancy",
                "median_occ_committed",
            ],
        )
        w.writeheader()
        for sys in ("CLN025", "AdK", "MBP"):
            methods = METHODS + (["TAPS"] if sys == "CLN025" else [])
            for m in methods:
                for tau in COMMIT_TAUS[sys]:
                    sub = [r for r in recs if r["system"] == sys and r["method"] == m and abs(r["tau_ps"] - tau) < 1e-9]
                    comm = [r for r in sub if r["committed"]]
                    occ = [100.0 * (r["occupancy"] or 0.0) for r in sub]
                    occ_c = [100.0 * (r["occupancy"] or 0.0) for r in comm]
                    ttc = [r["commit_ns"] for r in comm]
                    w.writerow(
                        {
                            "system": sys,
                            "method": m,
                            "tau_ps": tau,
                            "n_commit": len(comm),
                            "n": len(sub),
                            "p_commit": (len(comm) / len(sub)) if sub else 0.0,
                            "median_ttc": None if not ttc else float(np.median(ttc)),
                            "median_occupancy": None if not occ else float(np.median(occ)),
                            "median_occ_committed": None if not occ_c else float(np.median(occ_c)),
                        }
                    )


    marker = "## Commitment-threshold robustness"
    lines = [
        "",
        marker + " (existing cvs.npz; no new MD)",
        "Production τ: CLN025 40 ps (time sojourn); AdK/MBP 200 ps (consecutive frames, Δt = 2 ps).",
        "",
    ]
    for sys in ("CLN025", "AdK", "MBP"):
        methods = METHODS + (["TAPS"] if sys == "CLN025" else [])
        bits = []
        for m in methods:
            counts = []
            ttcs = []
            occs = []
            for tau in COMMIT_TAUS[sys]:
                sub = [r for r in recs if r["system"] == sys and r["method"] == m and abs(r["tau_ps"] - tau) < 1e-9]
                comm = [r for r in sub if r["committed"]]
                counts.append(str(len(comm)))
                if comm:
                    ttcs.append(f"{np.median([r['commit_ns'] for r in comm]):.1f}")
                else:
                    ttcs.append("—")
                occs.append(100.0 * (sub[0]["occupancy"] or 0.0) if sub else 0.0)
            bits.append(f"{m} {'/'.join(counts)}")
        occ_m = [r for r in recs if r["system"] == sys and r["method"] == "MOAS"]
        occ_med = 100.0 * float(np.median([r["occupancy"] or 0.0 for r in occ_m])) if occ_m else 0.0
        lines.append(
            f"{sys} τ = {'/'.join(str(int(t)) for t in COMMIT_TAUS[sys])} ps, commit n/3: "
            + "; ".join(bits)
            + f". MOAS occupancy {occ_med:.2f}% (τ-invariant)."
        )
    md = TAB / "results_summary.md"
    body = md.read_text(encoding="utf-8") if md.exists() else ""
    if marker in body:
        body = body[: body.index(marker)].rstrip() + "\n"
    md.write_text(body + "\n".join(lines) + "\n", encoding="utf-8")


def collect_residence() -> list[dict]:
    recs = []
    for (sys, method, rep), (kind, tag) in N3.items():
        t, mask = load_window_mask(kind, tag)
        if t is None:
            recs.append(
                {
                    "system": sys,
                    "method": method,
                    "rep": rep,
                    "tag": tag,
                    "n_sojourns": 0,
                    "median_rt": None,
                    "mean_rt": None,
                    "max_rt": 0.0,
                    "occupancy": None,
                    "sojourns": np.asarray([], dtype=float),
                }
            )
            continue
        sj = sojourns_ps(kind, mask, t)
        recs.append(
            {
                "system": sys,
                "method": method,
                "rep": rep,
                "tag": tag,
                "n_sojourns": int(len(sj)),
                "median_rt": None if len(sj) == 0 else float(np.median(sj)),
                "mean_rt": None if len(sj) == 0 else float(np.mean(sj)),
                "max_rt": 0.0 if len(sj) == 0 else float(np.max(sj)),
                "occupancy": float(np.mean(mask)),
                "sojourns": sj,
            }
        )
    return recs


def _window_occupancy(kind: str, z) -> list[tuple[float, float, str]]:
    """Return (x, occupancy_frac, xlabel-unit label) points for the window sweep."""
    if kind == "cln":
        rmsd = np.asarray(z["rmsd"], dtype=float)
        return [(c, float(np.mean(rmsd < c)), "RMSD cutoff (nm)") for c in CLN_RMSD_GRID]
    if kind == "adk":
        refs = json.loads((ROOT / "moas-adk/systems/adk/angle_refs.json").read_text())
        lid = np.asarray(z["lid"], dtype=float)
        nmp = np.asarray(z["nmp"], dtype=float)
        out = []
        for d in ADK_MARGIN_DEG:
            occ = float(np.mean((lid < refs["closed_lid_thr"] + d) & (nmp > refs["closed_nmp_thr"] - d)))
            out.append((d, occ, "window margin (deg)"))
        return out
    refs = json.loads((ROOT / "moas-mbp/systems/mbp/cv_refs.json").read_text())
    dist = np.asarray(z["dist"], dtype=float)
    th = np.asarray(z["theta"], dtype=float)
    out = []
    for i, (dd, dt) in enumerate(MBP_WINDOW_EXPAND):
        occ = float(np.mean((dist < refs["closed_dist_thr"] + dd) & (th < refs["closed_theta_thr"] + dt)))
        out.append((float(i - 2), occ, "window expansion"))
    return out


def collect_window_occupancy() -> list[dict]:
    recs = []
    for (sys, method, rep), (kind, tag) in N3.items():
        z = load_campaign_z(kind, tag)
        if z is None:
            continue
        for x, occ, xlab in _window_occupancy(kind, z):
            recs.append(
                {
                    "system": sys,
                    "method": method,
                    "rep": rep,
                    "tag": tag,
                    "x": x,
                    "occupancy": occ,
                    "xlabel": xlab,
                }
            )
    return recs


def _emp_surv(durs: np.ndarray, t_grid: np.ndarray) -> np.ndarray:
    if len(durs) == 0:
        return np.zeros_like(t_grid, dtype=float)
    return np.array([float(np.mean(durs >= t)) for t in t_grid], dtype=float)


def fig_residence(res_recs: list[dict], win_recs: list[dict]):
    fig, axes = plt.subplots(3, 3, figsize=(10.8, 9.2))
    fig.subplots_adjust(hspace=0.46, wspace=0.32)
    systems = ["CLN025", "AdK", "MBP"]
    t_max = {"CLN025": 600.0, "AdK": 3.0e4, "MBP": 5.0e4}
    win_prod_x = {"CLN025": 0.25, "AdK": 0.0, "MBP": 0.0}
    for j, sys in enumerate(systems):
        methods = METHODS + (["TAPS"] if sys == "CLN025" else [])
        tau = PROD_TAU[sys]
        t_grid = np.logspace(np.log10(2.0), np.log10(t_max[sys]), 250)

        ax = axes[0, j]
        panel(ax, "ABC"[j])
        ax.set_title(sys)
        ax.axvline(tau, color="#A0AEC0", ls=":", lw=1.05, zorder=1)
        for m in methods:
            curves = []
            for r in res_recs:
                if r["system"] != sys or r["method"] != m:
                    continue
                curves.append(_emp_surv(np.asarray(r["sojourns"], dtype=float), t_grid))
            if not curves:
                continue
            y = np.mean(np.vstack(curves), axis=0)
            ax.plot(
                t_grid,
                y,
                color=MC[m],
                lw=2.25 if m == "MOAS" else 1.35,
                ls="--" if m == "TAPS" else "-",
                zorder=4 if m == "MOAS" else 3,
                label=m,
            )
        ax.set_xscale("log")
        ax.set_ylim(-0.04, 1.08)
        ax.set_xlabel("residence time (ps)")
        if j == 0:
            ax.set_ylabel("P(T ≥ t)")
            ax.legend(frameon=False, loc="upper right", fontsize=6.5)

        ax = axes[1, j]
        panel(ax, "DEF"[j])
        ax.axhline(tau, color="#A0AEC0", ls=":", lw=1.05, zorder=1)
        for i, m in enumerate(methods):
            vals = [max(r["max_rt"], 1.0) for r in res_recs if r["system"] == sys and r["method"] == m]
            xs = np.full(len(vals), i, dtype=float) + (np.linspace(-0.12, 0.12, len(vals)) if len(vals) > 1 else [0.0])
            ax.scatter(xs, vals, c=MC[m], s=28, zorder=4, edgecolors="white", linewidths=0.3)
            if vals:
                ax.scatter([i], [float(np.median(vals))], marker="D", s=36, c=MC[m], zorder=5, edgecolors="white", linewidths=0.4)
        ax.set_xticks(range(len(methods)), methods, rotation=35, ha="right")
        ax.set_yscale("log")
        ax.set_ylabel("longest residence (ps)" if j == 0 else "")
        ax.set_ylim(0.8, t_max[sys] * 1.4)

        ax = axes[2, j]
        panel(ax, "GHI"[j])
        ax.axvline(win_prod_x[sys], color="#A0AEC0", ls=":", lw=1.05, zorder=1)
        xlab = None
        for m in methods:
            sub = [r for r in win_recs if r["system"] == sys and r["method"] == m]
            if not sub:
                continue
            xlab = sub[0]["xlabel"]
            xs = sorted({r["x"] for r in sub})
            ys = []
            for x in xs:
                occ = [100.0 * r["occupancy"] for r in sub if abs(r["x"] - x) < 1e-12]
                ys.append(float(np.median(occ)) if occ else np.nan)
            ax.plot(
                xs,
                np.clip(ys, 1e-3, None),
                color=MC[m],
                lw=2.25 if m == "MOAS" else 1.35,
                ls="--" if m == "TAPS" else "-",
                marker="^" if m == "TAPS" else "o",
                ms=5.0,
                zorder=4 if m == "MOAS" else 3,
            )
        ax.set_yscale("log")
        ax.set_ylim(8e-4, 80)
        if sys == "MBP":
            ax.set_xticks([-2, -1, 0, 1, 2], ["−2", "−1", "0", "+1", "+2"])
        ax.set_xlabel(xlab or "window")
        if j == 0:
            ax.set_ylabel("median occupancy (%)")
    save(fig, "figS2_residence")


def write_residence_tables(res_recs: list[dict], win_recs: list[dict]):
    TAB.mkdir(parents=True, exist_ok=True)
    dest = TAB / "residence_time_summary.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "system",
                "method",
                "n_campaigns",
                "n_sojourns",
                "median_n_sojourns",
                "median_rt",
                "mean_rt",
                "median_max_rt",
                "longest_rt",
                "p_sojourn_ge_tau",
                "median_occupancy",
            ],
        )
        w.writeheader()
        for sys in ("CLN025", "AdK", "MBP"):
            methods = METHODS + (["TAPS"] if sys == "CLN025" else [])
            tau = PROD_TAU[sys]
            for m in methods:
                sub = [r for r in res_recs if r["system"] == sys and r["method"] == m]
                all_s = np.concatenate([np.asarray(r["sojourns"], dtype=float) for r in sub]) if sub else np.array([])
                n_per = [r["n_sojourns"] for r in sub]
                maxes = [r["max_rt"] for r in sub]
                meds = [r["median_rt"] for r in sub if r["median_rt"] is not None]
                means = [r["mean_rt"] for r in sub if r["mean_rt"] is not None]
                occ = [100.0 * (r["occupancy"] or 0.0) for r in sub]
                survs = []
                for r in sub:
                    sj = np.asarray(r["sojourns"], dtype=float)
                    survs.append(0.0 if len(sj) == 0 else float(np.mean(sj >= tau)))
                w.writerow(
                    {
                        "system": sys,
                        "method": m,
                        "n_campaigns": len(sub),
                        "n_sojourns": int(sum(n_per)),
                        "median_n_sojourns": None if not n_per else float(np.median(n_per)),
                        "median_rt": None if not meds else float(np.median(meds)),
                        "mean_rt": None if not means else float(np.median(means)),
                        "median_max_rt": None if not maxes else float(np.median(maxes)),
                        "longest_rt": None if not maxes else float(np.max(maxes)),
                        "p_sojourn_ge_tau": None if not survs else float(np.mean(survs)),
                        "median_occupancy": None if not occ else float(np.median(occ)),
                    }
                )
    dest2 = TAB / "residence_time_replicates.csv"
    with dest2.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["system", "method", "rep", "tag", "n_sojourns", "median_rt", "mean_rt", "max_rt", "occupancy"],
        )
        w.writeheader()
        for r in res_recs:
            w.writerow({k: r[k] for k in ["system", "method", "rep", "tag", "n_sojourns", "median_rt", "mean_rt", "max_rt", "occupancy"]})
    dest3 = TAB / "window_occupancy.csv"
    with dest3.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["system", "method", "rep", "tag", "x", "occupancy", "xlabel"])
        w.writeheader()
        for r in win_recs:
            w.writerow(r)
    dest4 = TAB / "window_occupancy_summary.csv"
    with dest4.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["system", "method", "x", "median_occupancy"])
        w.writeheader()
        for sys in ("CLN025", "AdK", "MBP"):
            methods = METHODS + (["TAPS"] if sys == "CLN025" else [])
            xs = sorted({r["x"] for r in win_recs if r["system"] == sys})
            for m in methods:
                for x in xs:
                    occ = [100.0 * r["occupancy"] for r in win_recs if r["system"] == sys and r["method"] == m and abs(r["x"] - x) < 1e-12]
                    w.writerow(
                        {
                            "system": sys,
                            "method": m,
                            "x": x,
                            "median_occupancy": None if not occ else float(np.median(occ)),
                        }
                    )


def save(fig, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def _surv_times(sub: list[dict], budget: float):
    times, events = [], []
    for r in sub:
        if r.get("missing"):
            continue
        if r.get("commit") is not None:
            times.append(float(r["commit"]))
            events.append(True)
        else:
            t = r.get("sim_ns")
            times.append(float(t) if t is not None else budget)
            events.append(False)
    return np.asarray(times, dtype=float), np.asarray(events, dtype=bool)


def kaplan_meier(times: np.ndarray, events: np.ndarray, t_end: float):
    """Right-censored KM of P(not yet committed). Returns step times and survival."""
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=bool)
    ts = [0.0]
    ss = [1.0]
    s = 1.0
    ev = np.sort(times[events])
    for te in np.unique(ev):
        at_risk = int(np.sum(times >= te - 1e-12))
        d = int(np.sum((np.abs(times - te) < 1e-9) & events))
        if at_risk <= 0 or d <= 0:
            continue
        s *= 1.0 - d / at_risk
        ts.append(float(te))
        ss.append(float(s))
    ts.append(float(t_end))
    ss.append(float(s))
    return np.asarray(ts), np.asarray(ss)


def km_median(times: np.ndarray, events: np.ndarray):
    t, s = kaplan_meier(times, events, float(np.max(times)) if len(times) else 0.0)
    hit = np.where(s <= 0.5)[0]
    if len(hit) == 0:
        return None
    return float(t[hit[0]])


def bootstrap_block(sub: list[dict], budget: float, rng: np.random.Generator):
    times, events = _surv_times(sub, budget)
    occ = np.asarray([100.0 * (r.get("occ") or 0.0) for r in sub if not r.get("missing")], dtype=float)
    n = len(times)
    p_hat = float(events.mean()) if n else 0.0
    med_hat = km_median(times, events)
    occ_hat = float(np.median(occ)) if len(occ) else 0.0
    p_b, med_b, occ_b = [], [], []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, n)
        tb, eb = times[idx], events[idx]
        p_b.append(float(eb.mean()))
        m = km_median(tb, eb)
        med_b.append(np.nan if m is None else m)
        occ_b.append(float(np.median(occ[idx])))
    p_b, occ_b = np.asarray(p_b), np.asarray(occ_b)
    med_b = np.asarray(med_b, dtype=float)

    def ci(arr):
        return float(np.nanpercentile(arr, 2.5)), float(np.nanpercentile(arr, 97.5))

    med_ok = med_b[np.isfinite(med_b)]
    return {
        "n": n,
        "n_commit": int(events.sum()),
        "p_commit": p_hat,
        "p_lo": ci(p_b)[0],
        "p_hi": ci(p_b)[1],
        "median_ttc": med_hat,
        "median_lo": float(np.percentile(med_ok, 2.5)) if len(med_ok) else None,
        "median_hi": float(np.percentile(med_ok, 97.5)) if len(med_ok) else None,
        "frac_median_defined": float(np.isfinite(med_b).mean()),
        "occupancy": occ_hat,
        "occ_lo": ci(occ_b)[0],
        "occ_hi": ci(occ_b)[1],
    }


def panel(ax, letter: str):
    ax.text(
        -0.12,
        1.08,
        letter,
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        va="bottom",
        ha="left",
    )


def commit_gap_chart(ax, rows: list[dict], sys: str, show_legend: bool = False):
    """n = 3 commitment as a gap chart: filled marker is n_committed, open marker is 3/3."""
    for i, m in enumerate(METHODS):
        n_ok = 0
        for rep in range(3):
            r = rows_lookup(rows, sys, m, rep)
            if r and not r["missing"] and r["commit"] is not None:
                n_ok += 1
        if n_ok < 3:
            ax.plot([n_ok, 3], [i, i], color="#CBD5E0", lw=1.9, zorder=1, solid_capstyle="round")
            ax.scatter(
                [3],
                [i],
                s=52,
                facecolors="#FFFFFF",
                edgecolors="#A0AEC0",
                linewidths=1.25,
                zorder=3,
            )
        if n_ok > 0:
            ax.plot([0, n_ok], [i, i], color=MC[m], lw=2.15, zorder=2, solid_capstyle="round")
        ax.scatter(
            [n_ok],
            [i],
            s=72,
            c=MC[m],
            edgecolors="white",
            linewidths=0.7,
            zorder=4,
        )
        ax.text(3.22, i, f"{n_ok}/3", ha="left", va="center", fontsize=8, color="#2D3748")
    ax.set_xlim(-0.35, 3.95)
    ax.set_ylim(-0.65, len(METHODS) - 0.35)
    ax.set_yticks(range(len(METHODS)), METHODS)
    ax.set_xticks([0, 1, 2, 3])
    ax.set_xlabel("committed replicates")
    ax.xaxis.grid(True, color="#EDF2F7", lw=0.8)
    ax.set_axisbelow(True)
    if show_legend:
        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=MC["MOAS"],
                markeredgecolor="white",
                markersize=8,
                label="committed",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="white",
                markeredgecolor="#A0AEC0",
                markersize=7,
                label="n = 3",
            ),
        ]
        ax.legend(handles=handles, frameon=False, loc="lower right", fontsize=7)


def occupancy_point_range(ax, rows: list[dict], sys: str, show_legend: bool = False):
    """n = 3 occupancy as a horizontal point-range (median + min–max)."""
    ymax = 0.0
    for i, m in enumerate(METHODS):
        ys = sorted(
            100 * (r["occ"] or 0)
            for r in rows
            if r["system"] == sys and r["method"] == m and not r["missing"]
        )
        if not ys:
            continue
        ymax = max(ymax, max(ys))
        ax.plot(
            [ys[0], ys[-1]],
            [i, i],
            color=MC[m],
            lw=1.8,
            solid_capstyle="round",
            zorder=2,
            alpha=0.9,
        )
        off = (np.arange(len(ys)) - (len(ys) - 1) / 2.0) * 0.14
        ax.scatter(
            ys,
            i + off,
            s=44,
            facecolors="white",
            edgecolors=MC[m],
            linewidths=1.25,
            zorder=3,
        )
        ax.scatter(
            [np.median(ys)],
            [i],
            s=72,
            marker="D",
            c=MC[m],
            edgecolors="white",
            linewidths=0.7,
            zorder=4,
        )
    ax.set_yticks(range(len(METHODS)), METHODS)
    ax.set_ylim(-0.7, len(METHODS) - 0.3)
    ax.set_xlabel("occupancy (%)")
    ax.set_xlim(left=-0.02 * max(ymax, 1.0), right=max(ymax * 1.12, 1.0))
    ax.xaxis.grid(True, color="#EDF2F7", lw=0.8)
    ax.set_axisbelow(True)
    if show_legend:
        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="white",
                markeredgecolor="#2D3748",
                markersize=7,
                label="replicate",
            ),
            Line2D(
                [0],
                [0],
                marker="D",
                color="none",
                markerfacecolor="#2D3748",
                markeredgecolor="white",
                markersize=7,
                label="median",
            ),
        ]
        ax.legend(handles=handles, frameon=False, loc="upper left", fontsize=7)


def box(ax, xy, w, h, text, fc="#EDF2F7", ec="#2D3748", fontsize=8):
    p = FancyBboxPatch(
        xy,
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=0.9,
        facecolor=fc,
        edgecolor=ec,
    )
    ax.add_patch(p)
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center", fontsize=fontsize, color="#1A202C")


def arrow(ax, p0, p1):
    ax.add_patch(
        FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=10, linewidth=0.9, color="#2D3748", shrinkA=1, shrinkB=1)
    )


def fig1_workflow():
    fig, axes = plt.subplots(2, 3, figsize=(10.2, 6.2))
    fig.subplots_adjust(wspace=0.28, hspace=0.38)

    # A cycle
    ax = axes[0, 0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    panel(ax, "A")
    ax.set_title("Adaptive cycle")
    box(ax, (2.6, 7.4), 4.8, 1.6, "Initial MD\n(pool of configs)")
    box(ax, (2.6, 5.1), 4.8, 1.6, "Score candidates\nNov + Bnd + Tgt")
    box(ax, (2.6, 2.8), 4.8, 1.6, "Diversity-constrained\nseed selection")
    box(ax, (2.6, 0.5), 4.8, 1.6, "Short MD  →  update pool")
    arrow(ax, (5.0, 7.4), (5.0, 6.7))
    arrow(ax, (5.0, 5.1), (5.0, 4.4))
    arrow(ax, (5.0, 2.8), (5.0, 2.1))
    ax.annotate(
        "",
        xy=(2.4, 8.0),
        xytext=(2.4, 1.3),
        arrowprops=dict(arrowstyle="-|>", color="#C53030", connectionstyle="arc3,rad=0.75", lw=1.1),
    )
    ax.text(0.55, 4.7, "repeat", color="#C53030", fontsize=8, rotation=90, va="center")

    # B novelty
    ax = axes[0, 1]
    panel(ax, "B")
    ax.set_title("Novelty  (inverse density)")
    rng = np.random.default_rng(0)
    dense = rng.normal([0.35, 0.4], 0.12, size=(400, 2))
    sparse = rng.uniform([0.55, 0.15], [0.95, 0.9], size=(80, 2))
    ax.scatter(dense[:, 0], dense[:, 1], s=6, c="#A0AEC0", lw=0)
    ax.scatter(sparse[:, 0], sparse[:, 1], s=18, c="#C53030", lw=0)
    ax.scatter([0.82], [0.78], s=90, facecolors="none", edgecolors="#C53030", linewidths=1.4)
    ax.text(0.82, 0.86, "high novelty", ha="center", fontsize=7, color="#C53030")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("CV 1")
    ax.set_ylabel("CV 2")

    # C boundary
    ax = axes[0, 2]
    panel(ax, "C")
    ax.set_title("Boundary  (LAST frontier)")
    cloud = rng.normal([0.45, 0.45], 0.16, size=(500, 2))
    cloud = cloud[(cloud[:, 0] > 0.05) & (cloud[:, 0] < 0.85) & (cloud[:, 1] > 0.08) & (cloud[:, 1] < 0.85)]
    ax.scatter(cloud[:, 0], cloud[:, 1], s=6, c="#A0AEC0", lw=0)
    edge = cloud[np.argsort(cloud[:, 0] + 0.4 * cloud[:, 1])[-12:]]
    ax.scatter(edge[:, 0], edge[:, 1], s=28, c="#2B6CB0", lw=0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("CV 1")
    ax.set_ylabel("CV 2")

    # D target
    ax = axes[1, 0]
    panel(ax, "D")
    ax.set_title("Target proximity")
    ax.scatter(cloud[:, 0], cloud[:, 1], s=6, c="#A0AEC0", lw=0)
    ax.add_patch(Rectangle((0.72, 0.68), 0.22, 0.24, fill=False, ec="#C53030", lw=1.3, ls="--"))
    ax.scatter([0.84], [0.80], s=80, c="#C53030", zorder=3)
    ax.text(0.83, 0.95, "target basin", ha="center", fontsize=7, color="#C53030")
    ax.annotate("", xy=(0.78, 0.74), xytext=(0.48, 0.40), arrowprops=dict(arrowstyle="-|>", color="#C53030", lw=1.1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("CV 1")
    ax.set_ylabel("CV 2")
    ax.text(0.48, 0.32, "toward target", fontsize=7, color="#C53030")

    # E ranking
    ax = axes[1, 1]
    panel(ax, "E")
    ax.set_title("Equal-percentile mix")
    names = ["Novelty", "Boundary", "Target"]
    vals = np.array([[0.9, 0.4, 0.2], [0.3, 0.85, 0.25], [0.2, 0.3, 0.95], [0.7, 0.7, 0.7]])
    im = ax.imshow(vals, cmap="Reds", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks([0, 1, 2], names, rotation=20)
    ax.set_yticks([0, 1, 2, 3], ["A", "B", "C", "MOAS pick"])
    ax.set_ylabel("candidate")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.08, label="rank")

    # F diversity
    ax = axes[1, 2]
    panel(ax, "F")
    ax.set_title("Diversity-constrained seeds")
    ax.scatter(cloud[:, 0], cloud[:, 1], s=5, c="#E2E8F0", lw=0)
    seeds = np.array([[0.25, 0.30], [0.55, 0.18], [0.78, 0.55], [0.40, 0.72], [0.68, 0.82], [0.18, 0.62]])
    ax.scatter(seeds[:, 0], seeds[:, 1], s=55, c="#C53030", zorder=3, label="selected seeds")
    for i, s in enumerate(seeds):
        circ = plt.Circle(s, 0.11, fill=False, ls=":", color="#C53030", lw=0.8)
        ax.add_patch(circ)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("CV 1")
    ax.set_ylabel("CV 2")
    ax.legend(frameon=False, loc="upper left", fontsize=7)

    save(fig, "fig1_workflow")


def load_cvs(kind: str, tag: str):
    d = campaign_dir(kind, tag)
    if d is None:
        return None
    p = d / "cvs.npz"
    if not p.exists():
        return None
    return np.load(p)


def run_frac(closed, t_ps, win_ns=5.0):
    t = t_ps / 1000.0
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.002
    w = max(1, int(round(win_ns / max(dt, 1e-9))))
    c = np.asarray(closed, dtype=np.float64)
    ker = np.ones(w) / w
    y = np.convolve(c, ker, mode="same")
    return t, y


def _plot_occ_trace(ax, t, y, color, label, hit=None, commit=None, zorder=3, lw=1.3):
    t = np.asarray(t, dtype=float)
    y = 100.0 * np.asarray(y, dtype=float)
    step = max(1, len(t) // 2200)
    sl = slice(None, None, step)
    ax.fill_between(t[sl], 0.0, y[sl], color=color, alpha=0.18, linewidth=0, zorder=zorder - 1)
    ax.plot(t[sl], y[sl], color=color, lw=lw, label=label, zorder=zorder)
    if hit is not None:
        ax.axvline(hit, color=color, ls=":", lw=0.8, alpha=0.75, zorder=zorder)
    if commit is not None:
        yi = float(np.interp(commit, t, y))
        ax.scatter(
            [commit],
            [yi],
            marker="D",
            s=32,
            c=color,
            edgecolors="white",
            linewidths=0.45,
            zorder=zorder + 2,
        )


def fig2_hit_vs_commit(rows: list[dict]):
    fig = plt.figure(figsize=(10.8, 8.6))
    gs0 = fig.add_gridspec(3, 1, height_ratios=[1.18, 1.10, 0.90], hspace=0.38)
    top = gs0[0].subgridspec(1, 2, wspace=0.28)
    mid = gs0[1].subgridspec(1, 3, wspace=0.22)
    systems = ["CLN025", "AdK", "MBP"]

    ax = fig.add_subplot(top[0, 0])
    panel(ax, "A")
    ax.set_title("CLN025: brief visits vs staying folded")
    for tag, lab, col, method, zord in (
        ("discover_taps", "TAPS", MC["TAPS"], "TAPS", 3),
        ("discover_last", "LAST", MC["LAST"], "LAST", 4),
        ("moas_static", "MOAS", MC["MOAS"], "MOAS", 5),
    ):
        z = load_cvs("cln", tag)
        if z is None:
            continue
        t, y = run_frac(z["rmsd"] < FOLD_RMSD, z["t_ps"], win_ns=2.0)
        rec = rows_lookup(rows, "CLN025", method, 0)
        _plot_occ_trace(
            ax,
            t,
            y,
            col,
            lab,
            hit=None,
            commit=None if rec is None else rec.get("commit"),
            zorder=zord,
            lw=1.45 if method == "MOAS" else 1.15,
        )
    ax.set_xlabel("simulation time (ns)")
    ax.set_ylabel("rolling folded occupancy (%)")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left", fontsize=7)

    ax = fig.add_subplot(top[0, 1])
    panel(ax, "B")
    ax.set_title("AdK: hitting the window is not staying")
    for tag, lab, col, method, zord in (
        ("adk_random", "Random", MC["Random"], "Random", 3),
        ("adk_static", "MOAS", MC["MOAS"], "MOAS", 5),
    ):
        z = load_cvs("adk", tag)
        if z is None:
            continue
        t, y = run_frac(z["closed"], z["t_ps"])
        rec = rows_lookup(rows, "AdK", method, 0)
        _plot_occ_trace(
            ax,
            t,
            y,
            col,
            lab,
            hit=None if rec is None else rec.get("hit"),
            commit=None if rec is None else rec.get("commit"),
            zorder=zord,
            lw=1.45 if method == "MOAS" else 1.15,
        )
    rnd = rows_lookup(rows, "AdK", "Random", 0)
    if rnd and rnd.get("hit") is not None:
        ax.text(rnd["hit"] + 3, 8, "first hit", fontsize=7, color=MC["Random"])
    ax.set_xlabel("simulation time (ns)")
    ax.set_ylabel("rolling closed occupancy (%)")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left", fontsize=7)

    for j, sys in enumerate(systems):
        ax = fig.add_subplot(mid[0, j])
        if j == 0:
            panel(ax, "C")
        ax.set_title(sys)
        for r in rows:
            if r["system"] != sys or r["missing"] or r["method"] == "TAPS":
                continue
            occ = 100 * (r["occ"] or 0)
            if r["hit"] is None:
                ax.scatter(
                    BUDGET[sys],
                    occ,
                    marker="o",
                    facecolors="none",
                    edgecolors=MC[r["method"]],
                    s=36,
                    lw=0.95,
                    zorder=3,
                )
            else:
                ax.scatter(
                    r["hit"],
                    occ,
                    marker="o",
                    c=MC[r["method"]],
                    s=38,
                    zorder=3,
                    edgecolors="white",
                    linewidths=0.35,
                )
        ax.set_xlabel("first-hit time (ns)")
        ax.set_yscale("symlog", linthresh=0.2)
        ax.set_ylim(bottom=0)
        if j == 0:
            ax.set_ylabel("target-basin occupancy (%)")
            ax.legend(
                handles=[
                    Line2D([0], [0], marker="o", color="none", markerfacecolor=MC[m], markersize=6.5, label=m)
                    for m in METHODS
                ],
                frameon=False,
                loc="upper right",
                fontsize=6.5,
            )

    ax = fig.add_subplot(gs0[2])
    panel(ax, "D")
    ax.set_title("Hit → committed conversion")
    methods_d = ["TAPS"] + METHODS
    sys_col = {"CLN025": "#9B2C2C", "AdK": "#2B6CB0", "MBP": "#2F855A"}
    sys_mk = {"CLN025": "o", "AdK": "s", "MBP": "D"}
    sys_off = {"CLN025": -0.22, "AdK": 0.0, "MBP": 0.22}
    for i, m in enumerate(methods_d):
        for sys in systems:
            sub = [r for r in rows if r["system"] == sys and r["method"] == m and not r["missing"]]
            if sys != "CLN025" and m == "TAPS":
                continue
            n_hit = sum(r["hit"] is not None for r in sub)
            n_c = sum(r["commit"] is not None for r in sub)
            y = i + sys_off[sys]
            if n_hit == 0:
                ax.scatter([0.0], [y], marker="x", s=22, c="#A0AEC0", linewidths=0.9, zorder=3)
                continue
            conv = n_c / n_hit
            ax.plot([0, conv], [y, y], color=sys_col[sys], lw=1.6, solid_capstyle="round", zorder=2)
            ax.scatter(
                [conv],
                [y],
                marker=sys_mk[sys],
                s=34,
                c=sys_col[sys],
                edgecolors="white",
                linewidths=0.35,
                zorder=4,
            )
    ax.set_yticks(range(len(methods_d)), methods_d)
    ax.set_xlabel("committed / first-hit")
    ax.set_xlim(-0.08, 1.12)
    ax.set_ylim(-0.55, len(methods_d) - 0.35)
    ax.axvline(1.0, color="#EDF2F7", lw=0.8)
    ax.legend(
        handles=[
            Line2D([0], [0], marker=sys_mk[s], color="none", markerfacecolor=sys_col[s], markersize=7, label=s)
            for s in systems
        ]
        + [Line2D([0], [0], marker="x", color="#A0AEC0", linestyle="none", markersize=6, label="no hit")],
        frameon=False,
        loc="lower right",
        fontsize=7,
        ncol=4,
    )

    save(fig, "fig2_hit_vs_commit")



def rows_lookup(rows, sys, method, rep):
    for r in rows:
        if r["system"] == sys and r["method"] == method and r["rep"] == rep:
            return r
    return None


def fig3_km(rows: list[dict]):
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 3.8))
    fig.subplots_adjust(wspace=0.28, top=0.90, bottom=0.28)
    systems = ["CLN025", "AdK", "MBP"]
    letters = "ABC"
    for ax, sys, letter in zip(axes, systems, letters):
        budget = BUDGET[sys]
        ax.set_title(f"({letter})  {sys}", fontsize=10, pad=6)
        for method in KM_METHODS:
            sub = [r for r in rows if r["system"] == sys and r["method"] == method and not r["missing"]]
            times, events = _surv_times(sub, budget)
            t, s = kaplan_meier(times, events, budget)
            ax.step(t, s, where="post", color=MC[method], lw=2.2 if method == "MOAS" else 1.4, label=method)
            cens = times[~events]
            if len(cens):
                sc = []
                for tc in cens:
                    i = int(np.searchsorted(t, tc, side="right") - 1)
                    sc.append(s[max(i, 0)])
                ax.scatter(cens, sc, marker="+", s=40, color=MC[method], linewidths=1.15, zorder=5)
        ax.set_xlim(0, budget)
        ax.set_ylim(-0.05, 1.12)
        ax.set_xlabel("simulation time (ns)")
        if ax is axes[0]:
            ax.set_ylabel("probability of not yet committing")
        ax.axhline(0.5, color="#CBD5E0", lw=0.6, ls=":")
    handles = [Line2D([0], [0], color=MC[m], lw=2.2 if m == "MOAS" else 1.4, label=m) for m in KM_METHODS]
    handles.append(Line2D([0], [0], marker="+", color="#2D3748", linestyle="none", markersize=8, label="censored"))
    fig.legend(handles=handles, frameon=False, loc="lower center", ncol=6, bbox_to_anchor=(0.5, 0.0), fontsize=8)
    save(fig, "fig3_km")


def fig3_benchmark(rows: list[dict]):
    fig = plt.figure(figsize=(10.8, 8.4))
    gs = fig.add_gridspec(2, 3, hspace=0.52, wspace=0.38)
    systems = ["CLN025", "AdK", "MBP"]
    letters = "ABC"

    for i, sys in enumerate(systems):
        ax = fig.add_subplot(gs[0, i])
        panel(ax, letters[i])
        ax.set_title(f"{sys}  committed success")
        commit_gap_chart(ax, rows, sys, show_legend=False)

    # D time-to-commit
    ax = fig.add_subplot(gs[1, 0])
    panel(ax, "D")
    ax.set_title("Time to committed visit")
    for i, sys in enumerate(systems):
        for j, m in enumerate(METHODS):
            sub = [r for r in rows if r["system"] == sys and r["method"] == m and not r["missing"]]
            ys = [r["commit"] for r in sub if r["commit"] is not None]
            x = i + (j - 2) * 0.14
            if ys:
                ax.scatter([x] * len(ys), ys, c=MC[m], s=28, zorder=3, edgecolors="white", linewidths=0.3)
                ax.hlines(np.median(ys), x - 0.05, x + 0.05, color=MC[m], lw=1.4)
            else:
                ax.scatter([x], [BUDGET[sys]], c=MC[m], s=22, marker="x", lw=0.9)
    ax.set_xticks([0, 1, 2], systems)
    ax.set_ylabel("time to commit (ns)")
    ax.set_yscale("log")
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=MC[m], markersize=7, label=m) for m in METHODS]
    ax.legend(handles=handles, frameon=False, fontsize=7, loc="lower right")

    # E occupancy
    ax = fig.add_subplot(gs[1, 1])
    panel(ax, "E")
    ax.set_title("Target-basin occupancy")
    for i, sys in enumerate(systems):
        for j, m in enumerate(METHODS):
            sub = [r for r in rows if r["system"] == sys and r["method"] == m and not r["missing"]]
            ys = [100 * (r["occ"] or 0) for r in sub]
            x = i + (j - 2) * 0.14
            ax.scatter([x] * len(ys), ys, c=MC[m], s=28, zorder=3, edgecolors="white", linewidths=0.3)
            if ys:
                ax.hlines(np.median(ys), x - 0.05, x + 0.05, color=MC[m], lw=1.4)
    ax.set_xticks([0, 1, 2], systems)
    ax.set_ylabel("occupancy (%)")
    ax.set_yscale("symlog", linthresh=0.5)
    ax.set_ylim(bottom=0)

    # F outcome classification: no hit → hit only → committed
    ax = fig.add_subplot(gs[1, 2])
    panel(ax, "F")
    ax.set_title("Outcome classification")
    mat = np.full((len(METHODS), 9), np.nan)
    for j, m in enumerate(METHODS):
        col = 0
        for sys in systems:
            for rep in range(3):
                r = rows_lookup(rows, sys, m, rep)
                if r is None or r["missing"]:
                    mat[j, col] = np.nan
                elif r["commit"] is not None:
                    mat[j, col] = 2
                elif r["hit"] is not None:
                    mat[j, col] = 1
                else:
                    mat[j, col] = 0
                col += 1
    cmap = mpl.colors.ListedColormap(["#E2E8F0", "#DD6B20", "#C53030"])
    ax.imshow(mat, cmap=cmap, vmin=0, vmax=2, aspect="auto")
    ax.set_yticks(range(len(METHODS)), METHODS)
    xt = []
    for sys in systems:
        for rep in range(3):
            xt.append(f"{sys[0]}{rep}")
    ax.set_xticks(range(9), xt, fontsize=7)
    ax.axvline(2.5, color="white", lw=1.2)
    ax.axvline(5.5, color="white", lw=1.2)
    ax.set_xlabel("no hit  →  hit only  →  committed", fontsize=8)
    handles = [
        Patch(facecolor="#E2E8F0", edgecolor="#A0AEC0", label="No hit"),
        Patch(facecolor="#DD6B20", edgecolor="#C05621", label="Hit only"),
        Patch(facecolor="#C53030", edgecolor="#9B2C2C", label="Committed"),
    ]
    ax.legend(
        handles=handles,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.28),
        ncol=3,
        fontsize=7,
        handlelength=0.9,
        columnspacing=0.8,
    )

    save(fig, "fig4_benchmark")


def fig4_occupancy(rows: list[dict]):
    fig = plt.figure(figsize=(10.8, 7.4))
    gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.36)
    systems = ["CLN025", "AdK", "MBP"]
    for i, sys in enumerate(systems):
        ax = fig.add_subplot(gs[0, i])
        panel(ax, "ABC"[i])
        ax.set_title(f"{sys} occupancy")
        occupancy_point_range(ax, rows, sys, show_legend=(i == 0))

    # D landscapes AdK MOAS vs LAST
    ax = fig.add_subplot(gs[1, 0])
    panel(ax, "D")
    ax.set_title("AdK CV density")
    refs = json.loads((ROOT / "moas-adk/systems/adk/angle_refs.json").read_text())
    for tag, lab, cmap, alpha in (
        ("adk_last", "LAST", "Blues", 0.55),
        ("adk_static", "MOAS", "Reds", 0.55),
    ):
        z = load_cvs("adk", tag)
        if z is None:
            continue
        ax.hexbin(z["lid"], z["nmp"], gridsize=35, cmap=cmap, mincnt=2, alpha=alpha, linewidths=0)
    ax.axvline(refs["closed_lid_thr"], color="#C53030", ls="--", lw=0.8)
    ax.axhline(refs["closed_nmp_thr"], color="#C53030", ls="--", lw=0.8)
    ax.scatter([refs["open_lid"]], [refs["open_nmp"]], marker="^", c="#2B6CB0", s=40, zorder=4, label="open")
    ax.scatter([refs["closed_lid"]], [refs["closed_nmp"]], marker="s", c="#C53030", s=40, zorder=4, label="closed")
    ax.set_xlabel("LID angle (deg)")
    ax.set_ylabel("NMP angle (deg)")
    ax.legend(frameon=False, loc="best", fontsize=7)

    # E MBP landscape
    ax = fig.add_subplot(gs[1, 1])
    panel(ax, "E")
    ax.set_title("MBP CV density")
    refs = json.loads((ROOT / "moas-mbp/systems/mbp/cv_refs.json").read_text())
    for tag, cmap, alpha in (("mbp_last", "Blues", 0.5), ("mbp_static", "Reds", 0.5)):
        z = load_cvs("mbp", tag)
        if z is None:
            continue
        idx = slice(None, None, 8)
        ax.hexbin(z["dist"][idx], z["theta"][idx], gridsize=35, cmap=cmap, mincnt=3, alpha=alpha, linewidths=0)
    ax.axvline(refs["closed_dist_thr"], color="#C53030", ls="--", lw=0.8)
    ax.axhline(refs["closed_theta_thr"], color="#C53030", ls="--", lw=0.8)
    ax.scatter([refs["open_dist"]], [refs["open_theta"]], marker="^", c="#2B6CB0", s=40, zorder=4, label="open")
    ax.scatter([refs["closed_dist"]], [refs["closed_theta"]], marker="s", c="#C53030", s=40, zorder=4, label="closed")
    ax.set_xlabel("domain distance (nm)")
    ax.set_ylabel("hinge angle (deg)")
    ax.legend(frameon=False, fontsize=7)

    # F occupancy after hit
    ax = fig.add_subplot(gs[1, 2])
    panel(ax, "F")
    ax.set_title("Occupancy among campaigns that hit")
    for m in METHODS:
        xs, ys = [], []
        for r in rows:
            if r["method"] != m or r["missing"] or r["hit"] is None:
                continue
            xs.append({"CLN025": 0, "AdK": 1, "MBP": 2}[r["system"]] + (METHODS.index(m) - 2) * 0.12)
            ys.append(100 * (r["occ"] or 0))
        ax.scatter(xs, ys, c=MC[m], s=28, label=m, edgecolors="white", linewidths=0.3, zorder=3)
    ax.set_xticks([0, 1, 2], systems)
    ax.set_ylabel("occupancy (%)")
    ax.set_yscale("symlog", linthresh=0.5)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=7)

    save(fig, "fig5_occupancy")


def fig5_ablation():
    adk = {k: ablation_record("adk", tag) for k, tag in ADK_ABLATION.items()}
    mbp = {k: ablation_record("mbp", tag) for k, tag in MBP_ABLATION.items()}
    fig = plt.figure(figsize=(10.8, 8.2))
    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.32)

    def occ_traj(ax, blob, budget, letter, title):
        panel(ax, letter)
        ax.set_title(title)
        for k in AB_ORDER:
            m = blob.get(k)
            if m is None or not m.get("traj"):
                continue
            t = np.asarray([p[0] for p in m["traj"]], dtype=float)
            y = 100.0 * np.asarray([p[1] for p in m["traj"]], dtype=float)
            lw = 2.3 if k == "moas" else 1.25
            ax.plot(t, y, color=AB_COLOR[k], ls=AB_LS[k], lw=lw, label=AB_LABEL[k], zorder=4 if k == "moas" else 3)
            if m.get("commit") is not None:
                yi = float(np.interp(m["commit"], t, y))
                ax.scatter(
                    [m["commit"]],
                    [yi],
                    marker="D",
                    s=36,
                    c=AB_COLOR[k],
                    edgecolors="white",
                    linewidths=0.5,
                    zorder=5,
                )
        ax.set_xlim(0, budget)
        ax.set_xlabel("simulation time (ns)")
        ax.set_ylabel("cumulative occupancy (%)")
        ax.set_ylim(bottom=0)

    occ_traj(fig.add_subplot(gs[0, 0]), adk, BUDGET["AdK"], "A", "AdK occupancy vs time")
    ax_b = fig.add_subplot(gs[0, 1])
    occ_traj(ax_b, mbp, BUDGET["MBP"], "B", "MBP occupancy vs time")
    handles = [
        Line2D([0], [0], color=AB_COLOR[k], ls=AB_LS[k], lw=2.2 if k == "moas" else 1.3, label=AB_LABEL[k])
        for k in AB_ORDER
    ]
    ax_b.legend(handles=handles, frameon=False, loc="upper left", fontsize=7)

    ax = fig.add_subplot(gs[1, 0])
    panel(ax, "C")
    ax.set_title("Occupancy vs relative commit time")
    for sys, blob, marker in (("AdK", adk, "o"), ("MBP", mbp, "D")):
        budget = BUDGET[sys]
        for k in AB_ORDER:
            m = blob.get(k)
            if m is None:
                continue
            occ = 100.0 * (m["occ"] or 0.0)
            if m["commit"] is not None:
                x = float(m["commit"]) / budget
                ax.scatter(
                    [x],
                    [occ],
                    marker=marker,
                    s=64,
                    c=AB_COLOR[k],
                    edgecolors="white",
                    linewidths=0.5,
                    zorder=4,
                )
            else:
                x = 1.0 + 0.014 * (AB_ORDER.index(k) - 3)
                ax.scatter(
                    [x],
                    [occ],
                    marker=marker,
                    s=52,
                    facecolors="none",
                    edgecolors=AB_COLOR[k],
                    linewidths=1.15,
                    zorder=3,
                )
    ax.axvline(1.0, color="#E2E8F0", lw=0.8, ls=":")
    ax.set_xlim(0, 1.18)
    ax.set_xlabel("time to commit / budget")
    ax.set_ylabel("occupancy (%)")
    ax.set_yscale("symlog", linthresh=0.4)
    ax.set_ylim(bottom=0)
    sys_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#2D3748", markersize=7, label="AdK"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor="#2D3748", markersize=7, label="MBP"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="white",
            markeredgecolor="#2D3748",
            markersize=7,
            label="did not commit",
        ),
    ]
    ax.legend(handles=sys_handles, frameon=False, loc="upper left", fontsize=7)

    ax = fig.add_subplot(gs[1, 1])
    panel(ax, "D")
    ax.set_title("Three-objective simplex")
    verts = np.array([_barycentric(1, 0, 0), _barycentric(0, 1, 0), _barycentric(0, 0, 1)])
    ax.add_patch(Polygon(verts, closed=True, facecolor="#F7FAFC", edgecolor="#2D3748", lw=0.9, zorder=0))
    mid_nb = np.array(_barycentric(0.5, 0.5, 0.0))
    mid_nt = np.array(_barycentric(0.5, 0.0, 0.5))
    mid_bt = np.array(_barycentric(0.0, 0.5, 0.5))
    ax.plot([mid_nb[0], verts[2, 0]], [mid_nb[1], verts[2, 1]], color="#E2E8F0", lw=0.7, zorder=1)
    ax.plot([mid_nt[0], verts[1, 0]], [mid_nt[1], verts[1, 1]], color="#E2E8F0", lw=0.7, zorder=1)
    ax.plot([mid_bt[0], verts[0, 0]], [mid_bt[1], verts[0, 1]], color="#E2E8F0", lw=0.7, zorder=1)
    ax.text(*_barycentric(1.16, 0.0, 0.0), "Novelty", ha="center", va="bottom", fontsize=8)
    ax.text(*_barycentric(0.0, 1.18, -0.02), "Boundary", ha="center", va="top", fontsize=8)
    ax.text(*_barycentric(0.0, -0.02, 1.18), "Target", ha="center", va="top", fontsize=8)
    for sys, blob, marker, dx in (("AdK", adk, "o", -0.028), ("MBP", mbp, "D", 0.028)):
        for k in AB_ORDER:
            m = blob.get(k)
            if m is None:
                continue
            x, y = _barycentric(*AB_WEIGHTS[k])
            occ = float(m["occ"] or 0.0)
            s = 28 + 1400 * occ
            committed = m["commit"] is not None
            ax.scatter(
                [x + dx],
                [y],
                marker=marker,
                s=s,
                c=AB_COLOR[k] if committed else "white",
                edgecolors=AB_COLOR[k],
                linewidths=1.15,
                zorder=3 if k != "moas" else 4,
            )
    ax.set_aspect("equal")
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(-0.22, 1.05)
    ax.axis("off")
    ax.text(
        0.50,
        -0.14,
        "area ∝ occupancy;  filled = committed\ncircles AdK,  diamonds MBP",
        ha="center",
        va="top",
        fontsize=7,
        color="#4A5568",
        transform=ax.transAxes,
    )

    save(fig, "fig7_ablation")
    return adk, mbp


def load_seeds(kind: str, tag: str) -> list[dict]:
    d = campaign_dir(kind, tag)
    if d is None:
        return []
    rows = []
    for p in sorted(d.glob("seeds_round*.json")):
        rec = json.loads(p.read_text())
        rnd = rec.get("round")
        for s in rec.get("seeds") or []:
            s = dict(s)
            s["round"] = rnd
            rows.append(s)
    return rows


ROUND_CMAP = mpl.colors.LinearSegmentedColormap.from_list(
    "early_late", ["#2B6CB0", "#ECC94B", "#C53030"]
)
ROUND_NORM = mpl.colors.Normalize(vmin=1, vmax=15)


def _in_adk_window(lid, nmp, refs) -> bool:
    return float(lid) < float(refs["closed_lid_thr"]) and float(nmp) > float(refs["closed_nmp_thr"])


def _d_target(lid, nmp, refs) -> float:
    return float(np.hypot(float(lid) - refs["closed_lid"], float(nmp) - refs["closed_nmp"]))


def _seed_by_round(seeds: list[dict]) -> dict[int, list[dict]]:
    by: dict[int, list[dict]] = {}
    for s in seeds:
        by.setdefault(int(s["round"]), []).append(s)
    return by


def _draw_target_window(ax, refs, xlim, ylim):
    x0, x1 = xlim[0], float(refs["closed_lid_thr"])
    y0, y1 = float(refs["closed_nmp_thr"]), ylim[1]
    if x1 <= x0 or y1 <= y0:
        return
    ax.add_patch(
        Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            facecolor="#C53030",
            edgecolor="#C53030",
            linestyle="--",
            linewidth=0.8,
            alpha=0.12,
            zorder=1,
        )
    )


def _cloud_contour(ax, lid, nmp, color="#2B6CB0"):
    if lid is None or len(lid) < 50:
        return
    H, xe, ye = np.histogram2d(lid, nmp, bins=28)
    pos = H[H > 0]
    if pos.size == 0:
        return
    level = max(2.0, float(np.percentile(pos, 25)))
    xc = 0.5 * (xe[:-1] + xe[1:])
    yc = 0.5 * (ye[:-1] + ye[1:])
    ax.contour(xc, yc, H.T, levels=[level], colors=[color], linewidths=0.9, linestyles="--", zorder=2)


def _stage_spans(ax, *, labels=False):
    ax.axvspan(0.5, 5.5, color="#2B6CB0", alpha=0.08, zorder=0)
    ax.axvspan(5.5, 10.5, color="#D69E2E", alpha=0.10, zorder=0)
    ax.axvspan(10.5, 15.5, color="#C53030", alpha=0.08, zorder=0)
    if labels:
        for x, lab in ((3.0, "Exploration\nR1–R5"), (8.0, "Transition\nR6–R10"), (13.0, "Target-directed\nR11–R15")):
            ax.text(x, 0.98, lab, transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=7, color="#2D3748")


def _percentile_rank(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), dtype=np.float64)
    ranks[order] = np.linspace(0.0, 1.0, len(a), dtype=np.float64)
    return ranks


def _to_bins(lid, nmp, nbins, lo, hi):
    i = np.clip(((np.asarray(lid) - lo[0]) / (hi[0] - lo[0]) * nbins).astype(np.int64), 0, nbins - 1)
    j = np.clip(((np.asarray(nmp) - lo[1]) / (hi[1] - lo[1]) * nbins).astype(np.int64), 0, nbins - 1)
    return i, j


def _density_at(lid_all, nmp_all, lid_q, nmp_q, nbins, lo, hi):
    i, j = _to_bins(lid_all, nmp_all, nbins, lo, hi)
    hist = np.zeros((nbins, nbins), dtype=np.float64)
    np.add.at(hist, (i, j), 1)
    hist /= max(1.0, hist.sum())
    iq, jq = _to_bins(lid_q, nmp_q, nbins, lo, hi)
    return hist[iq, jq]


def _last_frontier_scores(lid_all, nmp_all, lid_q, nmp_q, nbins: int = 24) -> np.ndarray:
    z = np.stack([lid_all, nmp_all], axis=1)
    zq = np.stack([lid_q, nmp_q], axis=1)
    lo = z.min(axis=0) - 2.0
    hi = z.max(axis=0) + 2.0
    hist, xedges, yedges = np.histogram2d(z[:, 0], z[:, 1], bins=nbins, range=[[lo[0], hi[0]], [lo[1], hi[1]]])
    occ = hist > 0
    pad = np.pad(occ, 1, constant_values=False)
    empty_n = (~pad[:-2, 1:-1]) | (~pad[2:, 1:-1]) | (~pad[1:-1, :-2]) | (~pad[1:-1, 2:])
    frontier = occ & empty_n
    iq = np.clip(np.digitize(zq[:, 0], xedges) - 1, 0, nbins - 1)
    jq = np.clip(np.digitize(zq[:, 1], yedges) - 1, 0, nbins - 1)
    radius = np.linalg.norm(zq - z.mean(axis=0), axis=1)
    radius = radius / (float(radius.max()) + 1e-12)
    lat_rho = hist[iq, jq]
    lat_rho = lat_rho / (float(lat_rho.max()) + 1e-12)
    on_rim = frontier[iq, jq].astype(np.float64)
    return 1.5 * on_rim + radius * (1.0 - 0.5 * lat_rho)


def _adk_windows(segments, window=25, horizon=100, stride=5):
    extra = []
    for si, seg in enumerate(segments):
        lid, nmp, t_ps = seg["lid"], seg["nmp"], seg["t_ps"]
        n = len(lid)
        last_start = n - window - horizon
        if last_start < 0:
            continue
        starts = np.arange(0, last_start + 1, stride, dtype=np.int64)
        end = starts + window - 1
        extra.append(
            {
                "lid_end": lid[end],
                "nmp_end": nmp[end],
            }
        )
    return {
        "lid_end": np.concatenate([e["lid_end"] for e in extra]),
        "nmp_end": np.concatenate([e["nmp_end"] for e in extra]),
    }


def moas_adk_objective_ranks(tag: str = "adk_static") -> list[dict]:
    """Recompute mean novelty/boundary/target percentile ranks of the 6 MOAS seeds per round.

    Ranks are relative to that round's candidate pool. Weights stay equal; only the pool changes.
    """
    camp = ADK_CAMP / tag
    init_p = ROOT / "moas-adk/analysis/adk_open/cvs.npz"
    refs = json.loads((ROOT / "moas-adk/systems/adk/angle_refs.json").read_text())
    if not camp.exists() or not init_p.exists():
        return []
    data = np.load(init_p)
    mask = data["t_ps"] <= 20000.0 + 1e-6
    segments = [
        {
            "name": "cmd_init",
            "t_ps": data["t_ps"][mask],
            "lid": data["lid"][mask],
            "nmp": data["nmp"][mask],
        }
    ]
    rows = []
    for rid in range(1, 16):
        seed_p = camp / f"seeds_round{rid:02d}.json"
        if not seed_p.exists():
            break
        recs = json.loads(seed_p.read_text())["seeds"]
        pack = _adk_windows(segments)
        pool_lid = np.concatenate([s["lid"] for s in segments])
        pool_nmp = np.concatenate([s["nmp"] for s in segments])
        lo = np.array([pool_lid.min() - 2.0, pool_nmp.min() - 2.0])
        hi = np.array([pool_lid.max() + 2.0, pool_nmp.max() + 2.0])
        lid_e, nmp_e = pack["lid_end"], pack["nmp_end"]
        rho = _density_at(pool_lid, pool_nmp, lid_e, nmp_e, 24, lo, hi)
        inv = 1.0 / (rho + 1e-6)
        inv = inv / (inv.max() + 1e-12)
        last_sc = _last_frontier_scores(pool_lid, pool_nmp, lid_e, nmp_e)
        commit = 1.0 / (np.hypot(lid_e - refs["closed_lid"], nmp_e - refs["closed_nmp"]) + 5.0)
        pi_n = _percentile_rank(inv)
        pi_b = _percentile_rank(last_sc)
        pi_t = _percentile_rank(commit)
        idx = np.array([int(s["window_index"]) for s in recs], dtype=int)
        if np.any((idx < 0) | (idx >= len(lid_e))):
            break
        rows.append(
            {
                "round": rid,
                "nov": float(pi_n[idx].mean()),
                "bnd": float(pi_b[idx].mean()),
                "tgt": float(pi_t[idx].mean()),
                "mix": float(((pi_n + pi_b + pi_t)[idx] / 3.0).mean()),
            }
        )
        rnd_dir = camp / "adaptive" / f"round{rid:02d}"
        if not rnd_dir.exists():
            break
        for npz in sorted(rnd_dir.glob("seed_*_cvs.npz")):
            rank = npz.name.split("_")[1]
            z = np.load(npz)
            segments.append({"name": f"r{rid:02d}_s{rank}", "t_ps": z["t_ps"], "lid": z["lid"], "nmp": z["nmp"]})
    return rows


def fig6_mechanism():
    refs = json.loads((ROOT / "moas-adk/systems/adk/angle_refs.json").read_text())
    specs = [
        ("A", "Random", "adk_random", False, False),
        ("B", "LAST", "adk_last", True, False),
        ("C", "kNN-AS", "adk_s2_knn", False, False),
        ("D", "MOAS", "adk_static", False, True),
    ]
    packed = []
    lids_all, nmps_all = [], []
    for letter, name, tag, contour, centroid in specs:
        z = load_cvs("adk", tag)
        seeds = load_seeds("adk", tag)
        packed.append((letter, name, tag, contour, centroid, z, seeds))
        if z is not None:
            lids_all.append(z["lid"][::20])
            nmps_all.append(z["nmp"][::20])
    xlim = (float(np.min(np.concatenate(lids_all))) - 2.0, float(np.max(np.concatenate(lids_all))) + 2.0)
    ylim = (float(np.min(np.concatenate(nmps_all))) - 2.0, float(np.max(np.concatenate(nmps_all))) + 2.0)

    fig = plt.figure(figsize=(10.6, 13.2))
    gs = fig.add_gridspec(5, 2, height_ratios=[1.08, 1.08, 0.70, 0.70, 0.78], hspace=0.40, wspace=0.28)
    map_axes = [
        fig.add_subplot(gs[0, 0]),
        fig.add_subplot(gs[0, 1]),
        fig.add_subplot(gs[1, 0]),
        fig.add_subplot(gs[1, 1]),
    ]
    ax_e = fig.add_subplot(gs[2, :])
    ax_f = fig.add_subplot(gs[3, :], sharex=ax_e)
    ax_g = fig.add_subplot(gs[4, :], sharex=ax_e)

    last_sc = None
    for ax, (letter, name, tag, contour, centroid, z, seeds) in zip(map_axes, packed):
        panel(ax, letter)
        ax.set_title(name)
        if z is not None:
            idx = slice(None, None, 12)
            ax.hexbin(
                z["lid"][idx],
                z["nmp"][idx],
                gridsize=30,
                cmap="Greys",
                mincnt=2,
                linewidths=0,
                alpha=0.9,
                zorder=0,
            )
            if contour:
                _cloud_contour(ax, z["lid"][::8], z["nmp"][::8], color="#2B6CB0")
        _draw_target_window(ax, refs, xlim, ylim)
        ax.scatter(
            [refs["closed_lid"]],
            [refs["closed_nmp"]],
            marker="s",
            c="#C53030",
            s=28,
            zorder=4,
            edgecolors="white",
            linewidths=0.3,
        )
        if seeds:
            lid = np.array([s["lid"] for s in seeds], dtype=float)
            nmp = np.array([s["nmp"] for s in seeds], dtype=float)
            rnd = np.array([s["round"] for s in seeds], dtype=float)
            last_sc = ax.scatter(
                lid,
                nmp,
                c=rnd,
                cmap=ROUND_CMAP,
                norm=ROUND_NORM,
                s=22,
                zorder=3,
                edgecolors="white",
                linewidths=0.25,
            )
            if centroid:
                by = _seed_by_round(seeds)
                rounds = sorted(by)
                mlid = [float(np.mean([s["lid"] for s in by[r]])) for r in rounds]
                mnmp = [float(np.mean([s["nmp"] for s in by[r]])) for r in rounds]
                ax.plot(mlid, mnmp, color="#1A202C", lw=1.5, zorder=5, solid_capstyle="round")
                ax.scatter(
                    mlid,
                    mnmp,
                    c=rounds,
                    cmap=ROUND_CMAP,
                    norm=ROUND_NORM,
                    s=16,
                    zorder=6,
                    edgecolors="#1A202C",
                    linewidths=0.4,
                )
                ax.annotate("R1", (mlid[0], mnmp[0]), textcoords="offset points", xytext=(-10, 8), fontsize=7, color="#1A202C")
                ax.annotate(
                    "R15",
                    (mlid[-1], mnmp[-1]),
                    textcoords="offset points",
                    xytext=(6, -10),
                    fontsize=7,
                    color="#1A202C",
                )
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.set_xlabel("LID–CORE angle (deg)")
        ax.set_ylabel("NMP–CORE angle (deg)")

    if last_sc is not None:
        cbar = fig.colorbar(last_sc, ax=map_axes, fraction=0.025, pad=0.02)
        cbar.set_label("adaptive round (early → late)")
        cbar.set_ticks([1, 5, 10, 15])

    panel(ax_e, "E")
    panel(ax_f, "F")
    _stage_spans(ax_e, labels=True)
    _stage_spans(ax_f, labels=False)
    for letter, name, tag, contour, centroid, z, seeds in packed:
        by = _seed_by_round(seeds)
        rounds = sorted(by)
        if not rounds:
            continue
        frac, dist = [], []
        for r in rounds:
            qs = by[r]
            n = max(len(qs), 1)
            frac.append(sum(_in_adk_window(s["lid"], s["nmp"], refs) for s in qs) / n)
            dist.append(float(np.median([_d_target(s["lid"], s["nmp"], refs) for s in qs])))
        ax_e.plot(rounds, frac, color=MC[name], lw=1.5, marker="o", ms=4, label=name, zorder=3)
        ax_f.plot(rounds, dist, color=MC[name], lw=1.5, marker="o", ms=4, label=name, zorder=3)

    ax_e.set_ylabel(r"target-window seed fraction")
    ax_e.set_ylim(-0.05, 1.08)
    ax_e.legend(frameon=False, loc="center left", fontsize=8)
    ax_f.set_ylabel("median target distance (deg)")
    ax_f.set_xlim(0.5, 15.5)
    ax_f.set_xticks([1, 5, 10, 15])
    plt.setp(ax_e.get_xticklabels(), visible=False)
    plt.setp(ax_f.get_xticklabels(), visible=False)

    panel(ax_g, "G")
    _stage_spans(ax_g, labels=False)
    ranks = moas_adk_objective_ranks("adk_static")
    if ranks:
        rr = [r["round"] for r in ranks]
        ax_g.plot(rr, [r["nov"] for r in ranks], color=AB_COLOR["nov"], lw=1.6, marker="o", ms=4, label="novelty")
        ax_g.plot(rr, [r["bnd"] for r in ranks], color=AB_COLOR["bnd"], lw=1.6, marker="s", ms=4, label="boundary")
        ax_g.plot(rr, [r["tgt"] for r in ranks], color=AB_COLOR["tgt"], lw=1.6, marker="^", ms=4, label="target")
        ax_g.plot(rr, [r["mix"] for r in ranks], color="#4A5568", lw=1.0, ls=":", marker="none", label="equal-weight mix")
        TAB.mkdir(parents=True, exist_ok=True)
        with (TAB / "moas_adk_objective_ranks.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["round", "nov", "bnd", "tgt", "mix"])
            w.writeheader()
            w.writerows(ranks)
    ax_g.set_xlabel("adaptive round")
    ax_g.set_ylabel("selected-seed percentile rank")
    ax_g.set_ylim(0.62, 1.03)
    ax_g.legend(frameon=False, loc="lower left", fontsize=8, ncol=2)
    save(fig, "fig6_seeds")


def fig7_explore_vs_target(rows: list[dict]):
    systems = ["CLN025", "AdK", "MBP"]
    fig, axes = plt.subplots(1, 3, figsize=(10.8, 4.3), sharey=False)
    fig.subplots_adjust(wspace=0.28)
    for ax, sys, letter in zip(axes, systems, "ABC"):
        panel(ax, letter)
        ax.set_title(sys)
        for m in METHODS:
            sub = [
                r
                for r in rows
                if r["system"] == sys and r["method"] == m and not r["missing"] and r["coverage"] is not None
            ]
            if not sub:
                continue
            xs = np.asarray([100 * r["coverage"] for r in sub], dtype=float)
            ys = np.asarray([100 * (r["occ"] or 0) for r in sub], dtype=float)
            mx, my = float(np.median(xs)), float(np.median(ys))
            for x, y in zip(xs, ys):
                ax.plot([mx, x], [my, y], color=MC[m], lw=0.85, alpha=0.55, zorder=2, solid_capstyle="round")
            ax.scatter(xs, ys, c=MC[m], s=38, edgecolors="white", linewidths=0.45, zorder=3)
            ax.scatter(
                [mx],
                [my],
                marker="D",
                s=62,
                c=MC[m],
                edgecolors="white",
                linewidths=0.55,
                zorder=4,
            )
        ax.set_xlabel("CV-space coverage (%)")
        ax.set_yscale("symlog", linthresh=0.3)
        ax.set_ylim(bottom=0)
        if ax is axes[0]:
            ax.set_ylabel("target-basin occupancy (%)")
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=MC[m], markersize=7, label=m) for m in METHODS]
    handles += [
        Line2D(
            [0],
            [0],
            marker="D",
            color="none",
            markerfacecolor="#2D3748",
            markeredgecolor="white",
            markersize=7,
            label="median",
        )
    ]
    axes[0].legend(handles=handles, frameon=False, loc="upper left", fontsize=7)
    save(fig, "fig8_explore_vs_target")


def write_tables(rows: list[dict], adk_ab: dict, mbp_ab: dict):
    TAB.mkdir(parents=True, exist_ok=True)
    dest = TAB / "n3_metrics.csv"
    with dest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["system", "method", "rep", "tag", "sim_ns", "hit_ns", "commit_ns", "occupancy", "coverage", "missing"],
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "system": r["system"],
                    "method": r["method"],
                    "rep": r["rep"],
                    "tag": r["tag"],
                    "sim_ns": r["sim_ns"],
                    "hit_ns": r["hit"],
                    "commit_ns": r["commit"],
                    "occupancy": r["occ"],
                    "coverage": r["coverage"],
                    "missing": r["missing"],
                }
            )
    dest2 = TAB / "ablation_metrics.csv"
    with dest2.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "system",
                "combo",
                "tag",
                "hit_ns",
                "commit_ns",
                "lag_ns",
                "occupancy",
                "post_commit_occ",
                "late_occ",
                "complete",
            ],
        )
        w.writeheader()
        for sys, blob, mapping in (("AdK", adk_ab, ADK_ABLATION), ("MBP", mbp_ab, MBP_ABLATION)):
            for k in AB_ORDER:
                m = blob.get(k)
                w.writerow(
                    {
                        "system": sys,
                        "combo": AB_LABEL[k],
                        "tag": mapping[k],
                        "hit_ns": None if m is None else m["hit"],
                        "commit_ns": None if m is None else m["commit"],
                        "lag_ns": None if m is None else m.get("lag"),
                        "occupancy": None if m is None else m["occ"],
                        "post_commit_occ": None if m is None else m.get("post_occ"),
                        "late_occ": None if m is None else m.get("late_occ"),
                        "complete": None if m is None else m["complete"],
                    }
                )

    rng = np.random.default_rng(BOOT_SEED)
    boot_rows = []
    dest3 = TAB / "bootstrap_metrics.csv"
    with dest3.open("w", newline="", encoding="utf-8") as fh:
        fields = [
            "system",
            "method",
            "n",
            "n_commit",
            "p_commit",
            "p_lo",
            "p_hi",
            "median_ttc",
            "median_lo",
            "median_hi",
            "frac_median_defined",
            "occupancy",
            "occ_lo",
            "occ_hi",
        ]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for sys in ("CLN025", "AdK", "MBP"):
            for method in KM_METHODS:
                sub = [r for r in rows if r["system"] == sys and r["method"] == method and not r["missing"]]
                b = bootstrap_block(sub, BUDGET[sys], rng)
                rec = {"system": sys, "method": method, **b}
                w.writerow(rec)
                boot_rows.append(rec)

    lines = ["# Draft numbers for Results", ""]
    for sys in ("CLN025", "AdK", "MBP"):
        lines.append(f"## {sys}")
        for m in METHODS + (["TAPS"] if sys == "CLN025" else []):
            sub = [r for r in rows if r["system"] == sys and r["method"] == m and not r["missing"]]
            n_hit = sum(r["hit"] is not None for r in sub)
            n_c = sum(r["commit"] is not None for r in sub)
            occ = [100 * (r["occ"] or 0) for r in sub]
            commits = [r["commit"] for r in sub if r["commit"] is not None]
            med = f"{np.median(commits):.1f}" if commits else "n.d."
            extra = ""
            br = next((x for x in boot_rows if x["system"] == sys and x["method"] == m), None)
            if br:
                ttc = "n.r." if br["median_ttc"] is None else f"{br['median_ttc']:.1f}"
                extra = (
                    f"; KM median {ttc} ns "
                    f"(boot 95% {br['median_lo'] if br['median_lo'] is not None else 'n.r.'}"
                    f"–{br['median_hi'] if br['median_hi'] is not None else 'n.r.'}); "
                    f"P(commit) {br['p_commit']:.2f} [{br['p_lo']:.2f}, {br['p_hi']:.2f}]; "
                    f"occ {br['occupancy']:.2f}% [{br['occ_lo']:.2f}, {br['occ_hi']:.2f}]"
                )
            lines.append(
                f"- {m}: hit {n_hit}/3, commit {n_c}/3, "
                f"occupancy {np.median(occ):.2f}% (IQR {np.percentile(occ,25):.2f}–{np.percentile(occ,75):.2f}), "
                f"median commit {med} ns{extra}"
            )
        lines.append("")
    (TAB / "results_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    style()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = collect_n3()
    print("n=3 rows", len(rows), "missing", sum(r["missing"] for r in rows))
    fig1_workflow()
    print("wrote fig1")
    fig2_hit_vs_commit(rows)
    print("wrote fig2")
    fig3_km(rows)
    print("wrote fig3 km")
    fig3_benchmark(rows)
    print("wrote fig4")
    fig4_occupancy(rows)
    print("wrote fig5")
    adk_ab, mbp_ab = fig5_ablation()
    print("wrote fig7 ablation")
    fig6_mechanism()
    print("wrote fig6 seeds")
    fig7_explore_vs_target(rows)
    print("wrote fig8")
    tau_recs = collect_threshold_robustness()
    fig_commit_threshold(tau_recs)
    print("wrote figS1 commit threshold")
    write_tables(rows, adk_ab, mbp_ab)
    write_threshold_tables(tau_recs)
    res_recs = collect_residence()
    win_recs = collect_window_occupancy()
    fig_residence(res_recs, win_recs)
    print("wrote figS2 residence")
    write_residence_tables(res_recs, win_recs)
    print("tables in", TAB)
    print("figures in", OUT)


if __name__ == "__main__":
    main()

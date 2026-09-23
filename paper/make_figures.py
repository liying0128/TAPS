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
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

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
            "axes.spines.top": False,
            "axes.spines.right": False,
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


def save(fig, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


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

    fig.suptitle("Fig. 1   MOAS workflow", fontsize=12, fontweight="bold", y=0.98)
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


def fig2_hit_vs_commit(rows: list[dict]):
    fig = plt.figure(figsize=(10.4, 7.6))
    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.32)

    # A: CLN rolling folded occupancy
    ax = fig.add_subplot(gs[0, 0])
    panel(ax, "A")
    ax.set_title("CLN025: brief visits vs staying folded")
    for tag, lab, col in (
        ("discover_taps", "TAPS", MC["TAPS"]),
        ("discover_last", "LAST", MC["LAST"]),
        ("moas_static", "MOAS", MC["MOAS"]),
    ):
        z = load_cvs("cln", tag)
        if z is None:
            continue
        t, y = run_frac(z["rmsd"] < FOLD_RMSD, z["t_ps"], win_ns=2.0)
        ax.plot(t, 100 * y, color=col, lw=1.0, label=lab)
    ax.set_xlabel("simulation time (ns)")
    ax.set_ylabel("rolling folded occupancy (%)")
    ax.legend(frameon=False, loc="upper right")

    # B: AdK random (hit, no commit) vs MOAS closed occupancy running
    ax = fig.add_subplot(gs[0, 1])
    panel(ax, "B")
    ax.set_title("AdK: hitting the window is not staying")
    rnd = load_cvs("adk", "adk_random")
    moa = load_cvs("adk", "adk_static")

    if rnd is not None:
        t, y = run_frac(rnd["closed"], rnd["t_ps"])
        ax.plot(t, 100 * y, color=MC["Random"], lw=0.9, label="Random")
        hit = rows_lookup(rows, "AdK", "Random", 0)
        if hit and hit["hit"] is not None:
            ax.axvline(hit["hit"], color=MC["Random"], ls=":", lw=0.9)
            ax.text(hit["hit"] + 2, 8, "first hit", fontsize=7, color=MC["Random"])
    if moa is not None:
        t, y = run_frac(moa["closed"], moa["t_ps"])
        ax.plot(t, 100 * y, color=MC["MOAS"], lw=0.9, label="MOAS")
    ax.set_xlabel("simulation time (ns)")
    ax.set_ylabel("rolling closed occupancy (%)")
    ax.legend(frameon=False)

    # C: hit time vs occupancy
    ax = fig.add_subplot(gs[1, 0])
    panel(ax, "C")
    ax.set_title("First-hit time vs target occupancy")
    markers = {"CLN025": "o", "AdK": "s", "MBP": "D"}
    for r in rows:
        if r["missing"] or r["method"] == "TAPS":
            continue
        if r["hit"] is None:
            ax.scatter(
                BUDGET[r["system"]] * 1.02,
                100 * (r["occ"] or 0),
                marker=markers[r["system"]],
                facecolors="none",
                edgecolors=MC[r["method"]],
                s=36,
                lw=0.9,
            )
            continue
        ax.scatter(
            r["hit"],
            100 * (r["occ"] or 0),
            marker=markers[r["system"]],
            c=MC[r["method"]],
            s=36,
            zorder=3,
            edgecolors="white",
            linewidths=0.3,
        )
    ax.set_xlabel("first-hit time (ns)")
    ax.set_ylabel("target-basin occupancy (%)")
    ax.set_yscale("symlog", linthresh=0.2)
    ax.set_ylim(bottom=0)
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=MC[m], markersize=7, label=m) for m in METHODS]
    handles += [
        Line2D([0], [0], marker=markers[s], color="#2D3748", linestyle="none", markerfacecolor="white", markersize=7, label=s)
        for s in ("CLN025", "AdK", "MBP")
    ]
    ax.legend(handles=handles, frameon=False, ncol=2, loc="upper right", fontsize=7)

    # D conversion
    ax = fig.add_subplot(gs[1, 1])
    panel(ax, "D")
    ax.set_title("Hit → committed conversion (n = 3)")
    methods_d = METHODS + ["TAPS"]
    x = np.arange(len(methods_d))
    width = 0.22
    systems = ["CLN025", "AdK", "MBP"]
    sys_col = {"CLN025": "#9B2C2C", "AdK": "#2B6CB0", "MBP": "#2F855A"}
    for i, sys in enumerate(systems):
        conv = []
        for m in methods_d:
            sub = [r for r in rows if r["system"] == sys and r["method"] == m and not r["missing"]]
            if sys != "CLN025" and m == "TAPS":
                conv.append(np.nan)
                continue
            n_hit = sum(r["hit"] is not None for r in sub)
            n_c = sum(r["commit"] is not None for r in sub)
            conv.append(np.nan if n_hit == 0 else n_c / n_hit)
        ax.bar(x + (i - 1) * width, [0 if np.isnan(v) else v for v in conv], width=width, color=sys_col[sys], label=sys, alpha=0.9)
        for xi, v in zip(x + (i - 1) * width, conv):
            if np.isnan(v):
                ax.text(xi, 0.03, "—", ha="center", fontsize=7, color="#A0AEC0")
    ax.set_xticks(x, methods_d, rotation=20)
    ax.set_ylabel("committed / first-hit")
    ax.set_ylim(0, 1.18)
    ax.legend(frameon=False, ncol=3, loc="upper right")

    fig.suptitle("Fig. 2   First hit is not committed sampling", fontsize=12, fontweight="bold", y=0.98)
    save(fig, "fig2_hit_vs_commit")


def rows_lookup(rows, sys, method, rep):
    for r in rows:
        if r["system"] == sys and r["method"] == method and r["rep"] == rep:
            return r
    return None


def fig3_benchmark(rows: list[dict]):
    fig = plt.figure(figsize=(10.8, 8.0))
    gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.38)
    systems = ["CLN025", "AdK", "MBP"]
    letters = "ABC"

    for i, sys in enumerate(systems):
        ax = fig.add_subplot(gs[0, i])
        panel(ax, letters[i])
        ax.set_title(f"{sys}  committed success")
        n_ok = []
        for m in METHODS:
            sub = [r for r in rows if r["system"] == sys and r["method"] == m and not r["missing"]]
            n_ok.append(sum(r["commit"] is not None for r in sub))
        ax.bar(np.arange(len(METHODS)), n_ok, color=[MC[m] for m in METHODS], width=0.72)
        ax.set_ylim(0, 3.4)
        ax.set_yticks([0, 1, 2, 3])
        ax.set_ylabel("committed replicates")
        ax.set_xticks(np.arange(len(METHODS)), METHODS, rotation=25)
        for xi, v in enumerate(n_ok):
            ax.text(xi, v + 0.08, f"{v}/3", ha="center", fontsize=8)

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

    # F success matrix
    ax = fig.add_subplot(gs[1, 2])
    panel(ax, "F")
    ax.set_title("Replicate outcome")
    # 5 methods x 9 (3 sys x 3 rep)
    mat = np.full((len(METHODS), 9), np.nan)
    annot = [[""] * 9 for _ in METHODS]
    for j, m in enumerate(METHODS):
        col = 0
        for sys in systems:
            for rep in range(3):
                r = rows_lookup(rows, sys, m, rep)
                if r is None or r["missing"]:
                    annot[j][col] = "?"
                elif r["commit"] is not None:
                    mat[j, col] = 2
                    annot[j][col] = "C"
                elif r["hit"] is not None:
                    mat[j, col] = 1
                    annot[j][col] = "H"
                else:
                    mat[j, col] = 0
                    annot[j][col] = "—"
                col += 1
    cmap = mpl.colors.ListedColormap(["#EDF2F7", "#F6AD55", "#C53030"])
    ax.imshow(mat, cmap=cmap, vmin=0, vmax=2, aspect="auto")
    ax.set_yticks(range(len(METHODS)), METHODS)
    xt = []
    for sys in systems:
        for rep in range(3):
            xt.append(f"{sys[0]}{rep}")
    ax.set_xticks(range(9), xt, fontsize=7)
    for i in range(len(METHODS)):
        for j in range(9):
            ax.text(j, i, annot[i][j], ha="center", va="center", fontsize=7, color="white" if mat[i, j] == 2 else "#1A202C")
    ax.axvline(2.5, color="white", lw=1.2)
    ax.axvline(5.5, color="white", lw=1.2)
    ax.set_xlabel("C = commit   H = hit only")

    fig.suptitle("Fig. 3   Cross-system committed sampling", fontsize=12, fontweight="bold", y=0.98)
    save(fig, "fig3_benchmark")


def fig4_occupancy(rows: list[dict]):
    fig = plt.figure(figsize=(10.8, 7.4))
    gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.36)
    systems = ["CLN025", "AdK", "MBP"]
    for i, sys in enumerate(systems):
        ax = fig.add_subplot(gs[0, i])
        panel(ax, "ABC"[i])
        ax.set_title(f"{sys} occupancy")
        meds = []
        for m in METHODS:
            ys = [100 * (r["occ"] or 0) for r in rows if r["system"] == sys and r["method"] == m and not r["missing"]]
            meds.append(np.median(ys) if ys else 0)
            for k, y in enumerate(ys):
                ax.scatter(METHODS.index(m) + (k - 1) * 0.08, y, c="white", edgecolors=MC[m], s=22, zorder=3, lw=0.8)
        ax.bar(np.arange(len(METHODS)), meds, color=[MC[m] for m in METHODS], width=0.7, alpha=0.85)
        ax.set_xticks(np.arange(len(METHODS)), METHODS, rotation=25)
        ax.set_ylabel("occupancy (%)")

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

    fig.suptitle("Fig. 4   Persistent target-basin occupancy", fontsize=12, fontweight="bold", y=0.98)
    save(fig, "fig4_occupancy")


def fig5_ablation():
    adk = {k: load_metrics("adk", tag) for k, tag in ADK_ABLATION.items()}
    mbp = {k: load_metrics("mbp", tag) for k, tag in MBP_ABLATION.items()}
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.0))
    fig.subplots_adjust(hspace=0.42, wspace=0.32)

    ax = axes[0, 0]
    panel(ax, "A")
    ax.set_title("AdK committed visit (n = 1)")
    cols = []
    for k in AB_ORDER:
        m = adk.get(k)
        cols.append(1 if m and m["commit"] is not None else 0)
    ax.bar(range(len(AB_ORDER)), cols, color=[AB_COLOR[k] for k in AB_ORDER], width=0.7)
    ax.set_ylim(0, 1.25)
    ax.set_yticks([0, 1], ["no", "yes"])
    ax.set_xticks(range(len(AB_ORDER)), [AB_LABEL[k] for k in AB_ORDER], rotation=25)
    for i, k in enumerate(AB_ORDER):
        m = adk.get(k)
        if m and m["hit"] is not None and m["commit"] is None:
            ax.text(i, 0.08, "hit only", ha="center", fontsize=7, color="#4A5568")

    ax = axes[0, 1]
    panel(ax, "B")
    ax.set_title("AdK time to commit / occupancy")
    xs = np.arange(len(AB_ORDER))
    commits = [adk[k]["commit"] if adk.get(k) and adk[k]["commit"] is not None else np.nan for k in AB_ORDER]
    occ = [100 * adk[k]["occ"] if adk.get(k) and adk[k]["occ"] is not None else 0 for k in AB_ORDER]
    cplot = np.asarray(commits, dtype=float)
    bars_c = ax.bar(xs - 0.18, np.where(np.isfinite(cplot), cplot, 0.0), 0.36, color="#2B6CB0", label="commit ns")
    for b, v in zip(bars_c, cplot):
        if not np.isfinite(v):
            b.set_visible(False)
            ax.plot(b.get_x() + b.get_width() / 2, 4, marker="x", color="#A0AEC0", ms=5)
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.bar(xs + 0.18, occ, 0.36, color="#C53030", alpha=0.85, label="occupancy %")
    ax.set_xticks(xs, [AB_LABEL[k] for k in AB_ORDER], rotation=25)
    ax.set_ylabel("time to commit (ns)")
    ax2.set_ylabel("occupancy (%)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper left")

    ax = axes[1, 0]
    panel(ax, "C")
    ax.set_title("MBP committed visit (n = 1)")
    cols = []
    hatch = []
    for k in AB_ORDER:
        m = mbp.get(k)
        if m is None:
            cols.append(0)
            hatch.append(True)
        elif not m["complete"]:
            cols.append(1 if m["commit"] is not None else 0)
            hatch.append(True)
        else:
            cols.append(1 if m["commit"] is not None else 0)
            hatch.append(False)
    bars = ax.bar(range(len(AB_ORDER)), cols, color=[AB_COLOR[k] for k in AB_ORDER], width=0.7)
    for b, h in zip(bars, hatch):
        if h:
            b.set_hatch("///")
            b.set_edgecolor("#2D3748")
            b.set_linewidth(0.6)
    ax.set_ylim(0, 1.35)
    ax.set_yticks([0, 1], ["no", "yes"])
    ax.set_xticks(range(len(AB_ORDER)), [AB_LABEL[k] for k in AB_ORDER], rotation=25)
    for i, k in enumerate(AB_ORDER):
        m = mbp.get(k)
        note = []
        if m is None:
            note.append("missing")
        elif not m["complete"]:
            note.append("running")
        elif m["hit"] is not None and m["commit"] is None:
            note.append("hit only")
        if note:
            ax.text(i, 0.08, "\n".join(note), ha="center", fontsize=6.5, color="#4A5568")

    ax = axes[1, 1]
    panel(ax, "D")
    ax.set_title("MBP occupancy")
    occ = []
    for k in AB_ORDER:
        m = mbp.get(k)
        occ.append(100 * m["occ"] if m and m["occ"] is not None else 0)
    bars = ax.bar(range(len(AB_ORDER)), occ, color=[AB_COLOR[k] for k in AB_ORDER], width=0.7)
    for b, k in zip(bars, AB_ORDER):
        m = mbp.get(k)
        if m is None or not m["complete"]:
            b.set_hatch("///")
            b.set_edgecolor("#2D3748")
            b.set_linewidth(0.6)
    ax.set_xticks(range(len(AB_ORDER)), [AB_LABEL[k] for k in AB_ORDER], rotation=25)
    ax.set_ylabel("occupancy (%)")
    ax.set_yscale("symlog", linthresh=0.2)

    fig.suptitle("Fig. 5   Ablation of MOAS objectives", fontsize=12, fontweight="bold", y=0.98)
    save(fig, "fig5_ablation")
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


def fig6_mechanism():
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.2))
    fig.subplots_adjust(hspace=0.38, wspace=0.32)
    refs = json.loads((ROOT / "moas-adk/systems/adk/angle_refs.json").read_text())

    specs = [
        ("A", axes[0, 0], "adk_random", "Random seeds (AdK)"),
        ("B", axes[0, 1], "adk_last", "LAST seeds (AdK)"),
        ("C", axes[1, 0], "adk_s2_knn", "kNN-AS seeds (AdK s2)"),
        ("D", axes[1, 1], "adk_static", "MOAS seeds (AdK)"),
    ]
    for letter, ax, tag, title in specs:
        panel(ax, letter)
        ax.set_title(title)
        z = load_cvs("adk", tag if tag != "adk_s2_knn" else "adk_s2_knn")
        if z is not None:
            idx = slice(None, None, 15)
            ax.hexbin(z["lid"][idx], z["nmp"][idx], gridsize=28, cmap="Greys", mincnt=2, linewidths=0, alpha=0.85)
        seeds = load_seeds("adk", tag)
        if seeds:
            lid = [s["lid"] for s in seeds]
            nmp = [s["nmp"] for s in seeds]
            rnd = np.array([s["round"] for s in seeds], dtype=float)
            sc = ax.scatter(lid, nmp, c=rnd, cmap="coolwarm", s=22, zorder=3, edgecolors="white", linewidths=0.2)
            fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04, label="round")
        ax.axvline(refs["closed_lid_thr"], color="#C53030", ls="--", lw=0.7)
        ax.axhline(refs["closed_nmp_thr"], color="#C53030", ls="--", lw=0.7)
        ax.scatter([refs["closed_lid"]], [refs["closed_nmp"]], marker="s", c="#C53030", s=28, zorder=4)
        ax.set_xlabel("LID (deg)")
        ax.set_ylabel("NMP (deg)")

    fig.suptitle("Fig. 6   Seed selection in CV space (early → late rounds)", fontsize=12, fontweight="bold", y=0.98)
    save(fig, "fig6_seeds")


def fig7_explore_vs_target(rows: list[dict]):
    fig, ax = plt.subplots(figsize=(6.4, 5.0))
    panel(ax, "A")
    markers = {"CLN025": "o", "AdK": "s", "MBP": "D"}
    for r in rows:
        if r["missing"] or r["method"] == "TAPS" or r["coverage"] is None:
            continue
        ax.scatter(
            100 * r["coverage"],
            100 * (r["occ"] or 0),
            marker=markers[r["system"]],
            c=MC[r["method"]],
            s=42,
            edgecolors="white",
            linewidths=0.4,
            zorder=3,
        )
    ax.set_xlabel("CV-space coverage (%)")
    ax.set_ylabel("target-basin occupancy (%)")
    ax.set_yscale("symlog", linthresh=0.3)
    handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=MC[m], markersize=7, label=m) for m in METHODS]
    handles += [
        Line2D([0], [0], marker=markers[s], color="#2D3748", linestyle="none", markerfacecolor="white", markersize=7, label=s)
        for s in ("CLN025", "AdK", "MBP")
    ]
    ax.legend(handles=handles, frameon=False, loc="upper left", fontsize=8)
    ax.set_title("Exploration vs target-directed sampling")
    fig.suptitle("Fig. 7   Methods optimize different axes", fontsize=12, fontweight="bold")
    save(fig, "fig7_explore_vs_target")


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
        w = csv.DictWriter(fh, fieldnames=["system", "combo", "tag", "hit_ns", "commit_ns", "occupancy", "complete"])
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
                        "occupancy": None if m is None else m["occ"],
                        "complete": None if m is None else m["complete"],
                    }
                )

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
            lines.append(
                f"- {m}: hit {n_hit}/3, commit {n_c}/3, "
                f"occupancy {np.median(occ):.2f}% (IQR {np.percentile(occ,25):.2f}–{np.percentile(occ,75):.2f}), "
                f"median commit {med} ns"
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
    fig3_benchmark(rows)
    print("wrote fig3")
    fig4_occupancy(rows)
    print("wrote fig4")
    adk_ab, mbp_ab = fig5_ablation()
    print("wrote fig5")
    fig6_mechanism()
    print("wrote fig6")
    fig7_explore_vs_target(rows)
    print("wrote fig7")
    write_tables(rows, adk_ab, mbp_ab)
    print("tables in", TAB)
    print("figures in", OUT)


if __name__ == "__main__":
    main()

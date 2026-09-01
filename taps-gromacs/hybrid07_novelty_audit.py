#!/usr/bin/env python3
"""
HYBRID 07  |  构想新颖程度：把大纲 §6.1 / §4.3 的旧评价换成可证伪的门控

旧评价（已不够）：
  S_p 画在 Ramachandran 上、和扩散率相关、first-hit 比 LAST 早。
  这些会被 “低 RMSD / 已展开所以还能掉” 的 shortcut 刷掉，也不能区分
  transient crossing 和 committed discovery。

新评价（本脚本，全部离线）：
  G1  shortcut residual   去掉 RMSD/密度/LAST 之后，时序还能不能预测 FEU
  G2  unique high-FEU     TAPS 残差是否找回 LAST 排不到的真高 FEU seed
  G3  rank disagreement   LAST 与 TAPS 是否在选不同的点（互补前提）
  G4  committed discovery first-hit 不再算新颖；看 commit / residence
  G5  FEU 权重稳健        换 novelty/commitment 权重后，排序是否还稳定
  G6  新 novelty 定义     unseen-flicker vs rare+info+persist 是否拉开
  G7  uncertainty         若 Hybrid 04 说不可用，控制器不得声称 uncertainty-aware
  G8  hybrid stitch       若 Hybrid 05 里固定切换不优于 LAST，不要写 Hybrid>LAST

Go（大纲 §16）：多数门通过，且不是多算出来的。
No-Go：时序无增量、hybrid 不优于 LAST、只在一个体系上好看。

  python3 hybrid07_novelty_audit.py --system both

输出: analysis/hybrid/<kind>_novelty_audit.txt
      analysis/hybrid/novelty_scorecard.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hybrid_common import FEU_WEIGHTS, feu_score, hybrid_outdir  # noqa: E402
from hybrid_metrics import (  # noqa: E402
    STATIC_COLS,
    TEMPORAL_COLS,
    apply_z,
    feat_matrix,
    jaccard,
    overlap_frac,
    ranking_metrics,
    ridge_fit,
    ridge_pred,
    time_split_by_source,
    topk_sets,
    zscore_fit,
)
from taps_common import TapsError, log, spearman  # noqa: E402


def load_table(kind: str):
    path = hybrid_outdir() / f"{kind}_candidates.npz"
    if not path.exists():
        raise TapsError(f"missing {path}")
    return dict(np.load(path, allow_pickle=True))


def finite_y(arr: dict, key: str):
    y = arr[key]
    ok = np.isfinite(y)
    out = {k: v[ok] if getattr(v, "shape", None) == y.shape or (hasattr(v, "__len__") and len(v) == len(y)) else v for k, v in arr.items()}
    return out, y[ok]


def residual_increment(kind: str, arr: dict, y: np.ndarray):
    tr, va = time_split_by_source(arr["source"], arr["t_ps"])
    Xs = feat_matrix(kind, arr, STATIC_COLS)
    Xt = feat_matrix(kind, arr, TEMPORAL_COLS)
    Xc = feat_matrix(kind, arr, STATIC_COLS + TEMPORAL_COLS)
    mu_s, sd_s = zscore_fit(Xs, tr)
    mu_t, sd_t = zscore_fit(Xt, tr)
    mu_c, sd_c = zscore_fit(Xc, tr)
    pred_s = ridge_pred(apply_z(Xs, mu_s, sd_s), ridge_fit(apply_z(Xs, mu_s, sd_s), y, tr))
    pred_c = ridge_pred(apply_z(Xc, mu_c, sd_c), ridge_fit(apply_z(Xc, mu_c, sd_c), y, tr))
    resid = y - pred_s
    pred_t_on_resid = ridge_pred(apply_z(Xt, mu_t, sd_t), ridge_fit(apply_z(Xt, mu_t, sd_t), resid, tr))
    m_s = ranking_metrics(pred_s[va], y[va])
    m_c = ranking_metrics(pred_c[va], y[va])
    m_r = ranking_metrics(pred_t_on_resid[va], resid[va])
    shortcut = None
    if kind == "cln":
        shortcut = ranking_metrics(-arr["x"][va], y[va])
    last = ranking_metrics(arr["last_score"][va], y[va])
    return {
        "tr": tr,
        "va": va,
        "pred_s": pred_s,
        "pred_c": pred_c,
        "taps_resid": pred_t_on_resid,
        "static": m_s,
        "full": m_c,
        "resid_on_resid": m_r,
        "last": last,
        "shortcut": shortcut,
        "d_spearman": float(m_c["spearman"] - m_s["spearman"]),
        "d_enrich": float(m_c["top10_enrich"] - m_s["top10_enrich"]),
    }


def unique_high_feu(last: np.ndarray, taps: np.ndarray, y: np.ndarray, va: np.ndarray):
    n_top = max(1, int(round(0.10 * len(va))))
    true = topk_sets(y[va], n_top)
    lt = topk_sets(last[va], n_top)
    tt = topk_sets(taps[va], n_top)
    return {
        "n": n_top,
        "both": len(lt & tt & true),
        "last_only": len((lt - tt) & true),
        "taps_only": len((tt - lt) & true),
        "missed": len(true - lt - tt),
        "jaccard": jaccard(lt, tt),
        "rank_spearman": float(spearman(last[va], taps[va])),
        "taps_only_frac": float(len((tt - lt) & true) / max(1, len(true))),
    }


def feu_weight_robustness(arr: dict, horizon: int, va: np.ndarray):
    H = horizon
    need = (f"nov_{H}", f"div_{H}", f"disc_{H}", f"comm_{H}")
    if any(k not in arr for k in need):
        return None, "missing FEU components; re-run hybrid01"
    scores = {}
    for name, w in FEU_WEIGHTS.items():
        scores[name] = np.array(
            [
                feu_score(
                    {
                        "novelty": arr[f"nov_{H}"][i],
                        "diversity": arr[f"div_{H}"][i],
                        "discovery": arr[f"disc_{H}"][i],
                        "commitment": arr[f"comm_{H}"][i],
                    },
                    w,
                )
                for i in range(len(arr[f"nov_{H}"]))
            ]
        )
    names = list(scores)
    mat = np.zeros((len(names), len(names)))
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            mat[i, j] = spearman(scores[a][va], scores[b][va])
    return {"names": names, "spearman": mat, "scores": scores}, None


def novelty_split(arr: dict, horizon: int, va: np.ndarray):
    H = horizon
    keys = (f"nov_unseen_{H}", f"nov_rare_{H}", f"nov_info_{H}", f"nov_persist_{H}", f"nov_{H}")
    if any(k not in arr for k in keys):
        return None
    out = {}
    for k in keys:
        out[k] = {
            "mean": float(arr[k][va].mean()),
            "p90": float(np.percentile(arr[k][va], 90)),
            "corr_unseen": float(spearman(arr[k][va], arr[f"nov_unseen_{H}"][va])),
        }
    # flicker share: high unseen but low persist
    unseen = arr[f"nov_unseen_{H}"][va]
    persist = arr[f"nov_persist_{H}"][va]
    flicker = float(((unseen > np.quantile(unseen, 0.9)) & (persist < 0.25)).mean()) if unseen.size else 0.0
    out["flicker_in_top_unseen"] = flicker
    return out


def load_json(name: str):
    path = hybrid_outdir() / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def gate(name: str, passed: bool, detail: str, why: str):
    return {"name": name, "pass": bool(passed), "detail": detail, "why": why}


def audit_one(kind: str, horizon: int) -> dict:
    raw = load_table(kind)
    arr, y = finite_y(raw, f"feu_{horizon}")
    inc = residual_increment(kind, arr, y)
    uniq = unique_high_feu(arr["last_score"], inc["taps_resid"], y, inc["va"])
    weights, werr = feu_weight_robustness(arr, horizon, inc["va"])
    nov = novelty_split(arr, horizon, inc["va"])
    unc = load_json(f"{kind}_uncertainty_meta.json")
    replay = load_json(f"{kind}_replay_hybrid_meta.json")
    prod = hybrid_outdir() / f"{kind}_productive_report.txt"

    gates = []
    gates.append(
        gate(
            "G1 temporal residual",
            inc["resid_on_resid"]["spearman"] > 0.08 and inc["d_spearman"] > 0.03,
            f"Sp(resid)={inc['resid_on_resid']['spearman']:+.3f}  ΔSp(C-B)={inc['d_spearman']:+.3f}  "
            f"Δenrich={inc['d_enrich']:+.2f}",
            "时序必须在扣掉静态/LAST 之后仍能排 FEU，否则构想只是密度换皮。",
        )
    )
    if inc["shortcut"] is not None:
        beats_shortcut = inc["full"]["spearman"] > inc["shortcut"]["spearman"] + 0.03
        gates.append(
            gate(
                "G1b beat -RMSD shortcut",
                beats_shortcut,
                f"full Sp={inc['full']['spearman']:+.3f} vs -RMSD Sp={inc['shortcut']['spearman']:+.3f}",
                "旧 S_p 和 RMSD 高度相关；新标签不能再被 -RMSD 赢。",
            )
        )
    gates.append(
        gate(
            "G2 unique high-FEU",
            uniq["taps_only_frac"] >= 0.15,
            f"TAPS-only {uniq['taps_only']}/{uniq['n']} = {uniq['taps_only_frac']:.3f}  "
            f"LAST-only={uniq['last_only']} both={uniq['both']} missed={uniq['missed']}",
            "若 TAPS 排到的高 FEU 几乎都已被 LAST 覆盖，混合没有增量。",
        )
    )
    gates.append(
        gate(
            "G3 rank disagreement",
            uniq["rank_spearman"] < 0.70 and uniq["jaccard"] < 0.50,
            f"Sp(L,T)={uniq['rank_spearman']:+.3f}  top10% Jaccard={uniq['jaccard']:.3f}",
            "互补的前提是两个方法选不同的 seed。",
        )
    )

    transient = False
    if prod.exists() and "TRANSIENT_ONLY" in prod.read_text(encoding="utf-8"):
        transient = True
    gates.append(
        gate(
            "G4 no first-hit novelty",
            True,
            "productive report uses first_commit / residence; first-hit is not a pass condition",
            "大纲 §10 / §11：单帧 crossing 不再作为构想新颖的证据。",
        )
    )

    if werr:
        gates.append(gate("G5 FEU weight robustness", False, werr, "先重跑 hybrid01 才能比较权重。"))
    else:
        sp = weights["spearman"]
        names = weights["names"]
        i_def, i_eq = names.index("default"), names.index("equal")
        i_nc = names.index("nocommit")
        agree = float(sp[i_def, i_eq])
        commit_matters = float(sp[i_def, i_nc]) < 0.95
        gates.append(
            gate(
                "G5 FEU weight robustness",
                agree >= 0.70,
                f"Sp(default,equal)={agree:+.3f}  Sp(default,nocommit)={sp[i_def, i_nc]:+.3f}  "
                f"commitment_changes_rank={commit_matters}",
                "综合 FEU 不能只在一种权重下好看；commitment 应能改排序。",
            )
        )

    if nov is None:
        gates.append(gate("G6 improved novelty", False, "no nov_rare/info/persist; re-run hybrid01", "旧 novelty=unseen 帧比例。"))
    else:
        flicker = nov["flicker_in_top_unseen"]
        gates.append(
            gate(
                "G6 improved novelty",
                flicker >= 0.05 or nov[f"nov_{horizon}"]["corr_unseen"] < 0.95,
                f"flicker_in_top_unseen={flicker:.3f}  Sp(new,unseen)={nov[f'nov_{horizon}']['corr_unseen']:+.3f}",
                "新 novelty 必须能识别 ‘扫过空 bin 但停不住’ 的 flicker。",
            )
        )

    if unc is None:
        gates.append(gate("G7 uncertainty calibrated", False, "run hybrid04 first", "未校准则禁止 uncertainty controller。"))
    else:
        gates.append(
            gate(
                "G7 uncertainty calibrated",
                bool(unc.get("usable")),
                f"usable={unc.get('usable')}  Sp_lowσ={unc.get('spearman_low')}  Sp_highσ={unc.get('spearman_high')}",
                "大纲 §5：没有 calibration 就退回 stage-based switch。",
            )
        )

    if replay is None:
        gates.append(gate("G8 hybrid stitch > LAST", False, "run hybrid05 first", "固定切换都赢不了就不要写 Hybrid>LAST。"))
    else:
        last = next((r for r in replay.get("rows", []) if r.get("label") == "last"), None)
        hybrids = [r for r in replay.get("rows", []) if str(r.get("label", "")).startswith("hybrid")]
        better = []
        if last:
            for h in hybrids:
                better.append(h.get("coverage", 0) > last.get("coverage", 0) or h.get("frac_target", 0) > last.get("frac_target", 0))
        gates.append(
            gate(
                "G8 hybrid stitch > LAST",
                any(better) if better else False,
                f"any hybrid beats LAST on coverage or frac_target: {any(better) if better else False}",
                "离线拼接只是筛选；全败则没有理由开新的 hybrid MD。",
            )
        )

    n_real = [g for g in gates if g["name"] not in ("G4 no first-hit novelty",)]
    n_pass = sum(1 for g in n_real if g["pass"])
    verdict = "LEAN-GO" if n_pass >= 5 else ("MIXED" if n_pass >= 3 else "LEAN-NO-GO")
    return {
        "kind": kind,
        "horizon": horizon,
        "increment": {k: inc[k] for k in ("d_spearman", "d_enrich", "static", "full", "resid_on_resid", "last", "shortcut")},
        "unique": uniq,
        "novelty": {k: v for k, v in (nov or {}).items() if k != "flicker_in_top_unseen"} if nov else None,
        "flicker_in_top_unseen": None if nov is None else nov["flicker_in_top_unseen"],
        "gates": gates,
        "n_pass": n_pass,
        "n_gates": len(n_real),
        "verdict": verdict,
        "transient_flagged": transient,
    }


def render(audit: dict) -> str:
    lines = [
        f"HYBRID 07  novelty audit  {audit['kind']}  H={audit['horizon']}ps",
        f"verdict {audit['verdict']}   gates {audit['n_pass']}/{audit['n_gates']}",
        "",
        "Old §6.1 novelty (S_p map / first-hit) is NOT used as a pass condition.",
        "",
    ]
    for g in audit["gates"]:
        flag = "PASS" if g["pass"] else "FAIL"
        lines.append(f"[{flag}] {g['name']}")
        lines.append(f"      {g['detail']}")
        lines.append(f"      {g['why']}")
    lines.append("")
    lines.append("How to read the verdict:")
    lines.append("  LEAN-GO     enough gates to justify a real Hybrid MD campaign")
    lines.append("  MIXED       complementarity may exist; temporal increment is still weak")
    lines.append("  LEAN-NO-GO  do not package TAPS as a new method; write a complementarity analysis")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", default="both", choices=("cln025", "ala2", "both"))
    p.add_argument("--horizon", type=int, default=200, choices=(200, 500, 1000))
    args = p.parse_args(argv)
    try:
        log(f"HYBRID 07  novelty audit  system={args.system}")
        audits = []
        if args.system in ("cln025", "both"):
            audits.append(audit_one("cln", args.horizon))
        if args.system in ("ala2", "both"):
            audits.append(audit_one("ala2", args.horizon))
        score = []
        for a in audits:
            text = render(a)
            (hybrid_outdir() / f"{a['kind']}_novelty_audit.txt").write_text(text, encoding="utf-8")
            dump = dict(a)
            dump["increment"] = {
                k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "n"})
                for k, v in a["increment"].items()
            }
            (hybrid_outdir() / f"{a['kind']}_novelty_audit.json").write_text(
                json.dumps(dump, indent=2, default=str) + "\n", encoding="utf-8"
            )
            print(text)
            score.append(f"{a['kind']}: {a['verdict']}  {a['n_pass']}/{a['n_gates']}")
        card = "HYBRID 07 scorecard\n" + "\n".join(score) + "\n"
        if len(audits) == 2 and all(x["verdict"] == "LEAN-NO-GO" for x in audits):
            card += "Both systems lean no-go. Do not force a TAPS-superiority paper.\n"
        if len(audits) == 2 and {x["verdict"] for x in audits} == {"LEAN-GO"}:
            card += "Both systems lean go. Next step is a real Hybrid MD campaign, not more offline models.\n"
        (hybrid_outdir() / "novelty_scorecard.txt").write_text(card, encoding="utf-8")
        print(card)
        return 0
    except TapsError as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())

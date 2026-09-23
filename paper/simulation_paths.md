# MOAS 论文用到的模拟文件位置

记录 **n = 3 主比较、消融、CLN025 补充 TAPS** 所需轨迹与分析文件。日期 2026-09-22。  
作图脚本 `paper/make_figures.py` 先读本机 `history.json` / `cvs.npz`，没有则读 `paper/data/hist_55/` 里从 lan55 拷来的 history。

不要把 lan55 上的 `adk-r1`（`/home/ly/Sampling/baseline_unbiased_md/`，另一篇稿）混进这些表。

---

## 机器

| 角色 | 主机名 | 地址 | SSH | 仓库根 |
|------|--------|------|-----|--------|
| 本机（244） | `ly-MS-7D25` | `192.168.31.244` | — | `/home/ly/TAPS` |
| 远端（55） | `ly-ZHENGJIUZHE-REN9000-34IMZ` | `192.168.31.55` | `ssh lan55` | `/home/ly/TAPS`（布局相同） |

本机大文件盘：`/home/ly/data/TAPS`（`/dev/sda`）。若干目录是符号链接，路径仍写 `/home/ly/TAPS/...` 即可。

- 本机 CLN 的 `taps-gromacs/analysis` 和 `taps-gromacs/systems` → `/home/ly/data/TAPS/taps-gromacs/...`
- 本机部分 AdK / MBP analysis campaign 单独链到 `/home/ly/data/TAPS/moas-adk|moas-mbp/...`（表中标 `data盘`）

lan173（`10.27.138.173`）只做过 kNN 中转，当前数据以 244 和 55 为准。

---

## 两类目录

每个 campaign 有两棵树，tag 同名：

| 内容 | CLN025 | AdK | MBP |
|------|--------|-----|-----|
| **分析**（`history.json`、`cvs.npz`、`pool.json`、occupancy） | `taps-gromacs/analysis/cln025_unfolded/campaigns/<tag>/` | `moas-adk/analysis/adk_open/campaigns/<tag>/` | `moas-mbp/analysis/mbp_open/campaigns/<tag>/` |
| **轨迹**（`roundXX/seed_YY/md_short.{xtc,tpr,gro}`） | `taps-gromacs/systems/chignolin_cln025/water_unfolded/adaptive/campaigns/<tag>/` | `moas-adk/systems/adk/water_open/adaptive/campaigns/<tag>/` | `moas-mbp/systems/mbp/water_open/adaptive/campaigns/<tag>/` |

分析目录里作图最少需要 `history.json`。CLN025 的 committed visit 要从同目录 `cvs.npz` 按 RMSD `< 0.25 nm`、≥ 40 ps 重算。AdK / MBP 的 hit / commit / occupancy 直接在 `history.json`。

远端 history 的薄拷贝（多数只有 `history.json`）：

`/home/ly/TAPS/paper/data/hist_55/{cln,adk,mbp}/<tag>/`

例外：`hist_55/cln/discover_knn/` 另有 `cvs.npz`。

---

## 共享输入（本机 244，远端 55 各有一份同路径）

### 初始化 cMD（各方法共用）

| 体系 | 文件 |
|------|------|
| CLN025 | `taps-gromacs/systems/chignolin_cln025/water_unfolded/runs/md_100ns.{xtc,tpr,gro}`（campaign 只用前 10 ns） |
| AdK | `moas-adk/systems/adk/water_open/runs/md_20ns.{xtc,tpr}` |
| MBP | `moas-mbp/systems/mbp/water_open/runs/md_20ns.{xtc,tpr}` |

### 盒子 / 拓扑 / MDP

| 体系 | 目录 |
|------|------|
| CLN025 | `taps-gromacs/systems/chignolin_cln025/water_unfolded/`（`topol.top`、`npt.gro`、`mdp/`） |
| AdK | `moas-adk/systems/adk/water_open/`（同上） |
| MBP | `moas-mbp/systems/mbp/water_open/`（同上） |

### 参考结构与 CV 定义

| 体系 | 位置 |
|------|------|
| CLN025 结构 | `taps-gromacs/systems/chignolin_cln025/structures/`（`cln025_native.pdb` 等） |
| AdK 结构 | `moas-adk/systems/adk/structures/`（`adk_open.pdb`、`adk_closed.pdb`、1AKE/4AKE） |
| AdK 角参考 | `moas-adk/systems/adk/angle_refs.json` |
| MBP 结构 | `moas-mbp/systems/mbp/structures/`（`mbp_open.pdb`、`mbp_closed.pdb`、1OMP/1ANF） |
| MBP CV 参考 | `moas-mbp/systems/mbp/cv_refs.json` |

### 驱动脚本

| 体系 | 脚本 |
|------|------|
| CLN025 | `taps-gromacs/stage13_cln025_discover.py` |
| AdK | `moas-adk/stage_adk_discover.py` |
| MBP | `moas-mbp/stage_mbp_discover.py` |

---

## 主文 n = 3

列含义：`244` = 本机分析目录有完整 `history.json`（及通常有 `cvs.npz`）；`55` = 远端分析目录；`hist_55` = 本机薄拷贝。轨迹与分析在同一台机器、同一 tag 下。

### CLN025（budget 82 ns，12 轮 × 6 × 1 ns）

| 方法 | tag | 分析 / 轨迹在 |
|------|-----|----------------|
| Random | `moas_random` `moas_s1_random` `moas_s2_random` | 244 |
| LAST | `discover_last` `discover_s1_last` `discover_s2_last` | 244 |
| Least-counts | `discover_lc` `discover_s1_lc` `discover_s2_lc` | 244 |
| kNN-AS | `discover_knn` | **55**（`hist_55/cln/discover_knn/` 含 history + cvs.npz） |
| kNN-AS | `discover_s1_knn` `discover_s2_knn` | 244 |
| MOAS | `moas_static` `moas_s1_static` `moas_s2_static` | 244 |
| TAPS（SI only） | `discover_taps` `discover_s1_taps` `discover_s2_taps` | 244 |

### AdK（budget 200 ns，15 轮 × 6 × 2 ns）

| 方法 | tag | 分析 / 轨迹在 |
|------|-----|----------------|
| Random | `adk_random` | 244（analysis → data盘） |
| Random | `adk_s1_random` `adk_s2_random` | **55**（`hist_55/adk/`） |
| LAST | `adk_last` | 244（analysis → data盘） |
| LAST | `adk_s1_last` `adk_s2_last` | **55** |
| Least-counts | `adk_lc` | 244（analysis → data盘） |
| Least-counts | `adk_s1_lc` `adk_s2_lc` | **55** |
| kNN-AS | `adk_knn` `adk_s1_knn` | **55** |
| kNN-AS | `adk_s2_knn` | 244（analysis → data盘） |
| MOAS | `adk_static` | 244（analysis → data盘） |
| MOAS | `adk_s1_static` `adk_s2_static` | **55** |

### MBP（budget 1 μs，82 轮 × 6 × 2 ns）

| 方法 | tag | 分析 / 轨迹在 |
|------|-----|----------------|
| Random | `mbp_random` | 244（analysis → data盘） |
| Random | `mbp_s1_random` | **55** |
| Random | `mbp_s2_random` | 244（analysis → data盘） |
| LAST | `mbp_last` | 244（analysis → data盘） |
| LAST | `mbp_s1_last` | **55** |
| LAST | `mbp_s2_last` | 244 |
| Least-counts | `mbp_lc` | 244（analysis → data盘） |
| Least-counts | `mbp_s1_lc` | **55** |
| Least-counts | `mbp_s2_lc` | 244（analysis → data盘） |
| kNN-AS | `mbp_knn` | **55** 分析 + 55 轨迹（约 120 G）；本机另有轨迹拷贝 `/home/ly/data/TAPS/from_55/moas-mbp/systems/mbp/water_open/adaptive/campaigns/mbp_knn/` |
| kNN-AS | `mbp_s1_knn` | **55** |
| kNN-AS | `mbp_s2_knn` | 244 |
| MOAS | `mbp_static` | 244（analysis → data盘） |
| MOAS | `mbp_s1_static` | **55** |
| MOAS | `mbp_s2_static` | 244（analysis → data盘） |

---

## 消融（n = 1，Full MOAS = 上表 seed 0 的 static）

### AdK — 全部在本机 244

`moas-adk/analysis/adk_open/campaigns/` 与 `moas-adk/systems/adk/water_open/adaptive/campaigns/`：

| 组合 | tag |
|------|-----|
| Novelty | `adk_nov` |
| Boundary | `adk_bnd` |
| Target | `adk_tgt` |
| Nov+Bnd | `adk_novbnd` |
| Nov+Tgt | `adk_novtgt` |
| Bnd+Tgt | `adk_bndtgt` |
| Full MOAS | `adk_static` |

### MBP

| 组合 | tag | 位置 |
|------|-----|------|
| Novelty | `mbp_nov` | 244 |
| Boundary | `mbp_bnd` | 244 |
| Target | `mbp_tgt` | 244 |
| Nov+Bnd | `mbp_novbnd` | **55**（`hist_55/mbp/mbp_novbnd/`） |
| Nov+Tgt | `mbp_novtgt` | **244**（`hist_55` 也有 history 拷贝） |
| Bnd+Tgt | `mbp_bndtgt` | **55**（`hist_55/mbp/mbp_bndtgt/`） |
| Full MOAS | `mbp_static` | 244（analysis → data盘） |

---

## 远端 55 上、这篇稿会用到的 campaign 全集

SSH：`ssh lan55`。下列目录与本机相对路径相同。

**分析**

- `/home/ly/TAPS/taps-gromacs/analysis/cln025_unfolded/campaigns/discover_knn`
- `/home/ly/TAPS/moas-adk/analysis/adk_open/campaigns/{adk_knn,adk_s1_knn,adk_s1_last,adk_s1_lc,adk_s1_random,adk_s1_static,adk_s2_last,adk_s2_lc,adk_s2_random,adk_s2_static}`
- `/home/ly/TAPS/moas-mbp/analysis/mbp_open/campaigns/{mbp_knn,mbp_s1_knn,mbp_s1_last,mbp_s1_lc,mbp_s1_random,mbp_s1_static,mbp_novbnd,mbp_bndtgt}`

**轨迹**：把上面的 `analysis/.../campaigns/<tag>` 换成对应 `systems/.../adaptive/campaigns/<tag>`。  
55 上 AdK 的 analysis 目录本身是链到 `/home/ly/data/TAPS/moas-adk/analysis`。

从 55 只拉 history（已做过）：

```bash
rsync -av lan55:TAPS/moas-adk/analysis/adk_open/campaigns/<tag>/history.json \
  /home/ly/TAPS/paper/data/hist_55/adk/<tag>/
```

---

## 本机 244 上链到 data 盘的 analysis campaign

路径仍是 `/home/ly/TAPS/moas-*/analysis/.../<tag>`，真实文件在 `/home/ly/data/TAPS/...`：

- AdK：`adk_last` `adk_lc` `adk_random` `adk_s2_knn` `adk_static`
- MBP：`mbp_last` `mbp_lc` `mbp_random` `mbp_s2_lc` `mbp_s2_random` `mbp_s2_static` `mbp_static`

其余 244 上的 AdK/MBP campaign 在 NVMe `/`（仓库目录本身）。

---

## 派生表与图（本机）

| 文件 | 作用 |
|------|------|
| `paper/tables/n3_metrics.csv` | n = 3 hit / commit / occupancy |
| `paper/tables/ablation_metrics.csv` | 消融 |
| `paper/tables/results_summary.md` | 中位数摘要 |
| `paper/figures/fig1_workflow.{png,pdf}` … `fig8_explore_vs_target.{png,pdf}` | 主文图（含 Fig. 3 Kaplan–Meier） |
| `paper/MOAS_manuscript_draft.docx` | 主文 |
| `paper/MOAS_supporting_information.docx` | SI |

重算：

```bash
python3 /home/ly/TAPS/paper/make_figures.py
python3 /home/ly/TAPS/paper/build_docx.py
```

---

## 磁盘上有、这篇稿不用

- CLN：`moas_dynamic` / `moas_pareto`、`hybrid*`、`*_s3_*`、`discover_s3_*`
- lan55：`/home/ly/Sampling/baseline_unbiased_md/`（`adk-r1`，另一篇）
- `taps-gromacs` 里 alanine 体系
- 权重 / seed 数 / diversity 敏感性：从未跑

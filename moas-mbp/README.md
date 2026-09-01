# MOAS-MBP — four methods on apo maltose-binding protein

后续实验只保留四种方法：**Random、LAST、Least-counts、MOAS-static**。  
体系是 apo MBP（开态 1OMP 出发，闭态 1ANF 去掉麦芽糖作 CV 参考）。没有配体。不做 MdfA。

CLN025 的七种方法 × 三次重复仍留在 `../moas-gromacs`。AdK n=1 仍在 `../moas-adk`。这里不再重跑 TAPS / dynamic / Pareto。

## 和 CLN025 / AdK 不同的协议（不要照搬 82 ns / RMSD）

| | CLN025 | AdK | MBP（本目录） |
|---|---|---|---|
| 集体变量 | CA-RMSD, Rg | LID–CORE 角, NMP–CORE 角 | **N/C 结构域 CA-COM 距离, 铰链角** |
| 成功标准 | RMSD&lt;0.25 nm 且停留 ≥ 40 ps | 两角都进入闭态窗口 ≥ 200 ps | **两 CV 都进入闭态窗口且停留 ≥ 200 ps** |
| 起点 | 展开态 | 开态 apo | **开态 apo（1OMP）** |
| 初始化 | 10 ns | 20 ns | **20 ns** cMD（四种方法共用） |
| 短轨迹 | 1 ns × 6 × 12 | 2 ns × 6 × 15 | **2 ns × 6 seeds × 15 轮** |
| **每条总预算** | 82 ns | 200 ns | **200 ns**（20 + 180） |

力场仍是 AMBER99SB-ILDN + TIP3P，300 K，0.15 M NaCl。盒子缓冲 1.2 nm，**十二面体**（MBP 比 AdK 大，立方盒子太浪费水）。  
结构域定义写在 `mbp_cvs.py`：N 叶 1–109 + 264–309，C 叶 114–258 + 316–370。闭态窗口在 `systems/mbp/cv_refs.json`（prepare 后生成）。

## 命令（按顺序）

```bash
cd /home/ly/TAPS/moas-mbp

# 1) 下载 1OMP/1ANF + pdb2gmx + 溶剂化 + 离子（CPU）
bash scripts/prepare_mbp.sh

# 2) 开态 / 闭态 EM + 1 ns NVT + 1 ns NPT（GPU；等 CLN seed=3 跑完）
bash scripts/run_em_eq.sh

# 3) 开态 20 ns 无偏 cMD，作为自适应初始化
bash scripts/run_cmd_init.sh

# 4) 四种方法各一条 200 ns campaign（seed=0）。再加重复：SEED=1 bash scripts/run_discover.sh
bash scripts/run_discover.sh
```

`run_md.py` 可续跑：同一条命令再执行会跳过已完成步骤，并从 `.cpt` 接着跑。

n=1 先看有没有 committed 到达；成功后再补 seed=1 / seed=2。不要一上来跑七种方法。

## 目录

```
moas-mbp/
  systems/mbp/structures/     1OMP / 1ANF 清洗 PDB
  systems/mbp/gmx_common_*    pdb2gmx 后的蛋白
  systems/mbp/water_open/     生产起点（溶剂化开态）
  systems/mbp/water_closed/   闭态参考盒子
  systems/mbp/cv_refs.json    开/闭 CV 与闭态窗口（prepare 后生成）
  stage_mbp_discover.py       四方法自适应
  run_md.py                   EM / 平衡 / 生产
```

Campaign 标签：`mbp_random`、`mbp_last`、`mbp_lc`、`mbp_static`。

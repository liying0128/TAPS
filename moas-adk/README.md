# MOAS-AdK — four methods on apo adenylate kinase

后续实验只保留四种方法：**Random、LAST、Least-counts、MOAS-static**。  
体系是 apo AdK（开态 4AKE 出发，闭态 1AKE 去掉 AP5A 作角度参考）。没有配体。

CLN025 的七种方法 × 三次重复仍留在 `../moas-gromacs`，这里不再重跑 TAPS / dynamic / Pareto。

## 和 CLN025 不同的协议（不要照搬 82 ns / RMSD）

| | CLN025 | AdK（本目录） |
|---|---|---|
| 集体变量 | CA-RMSD, Rg | LID–CORE 角, NMP–CORE 角 |
| 成功标准 | RMSD&lt;0.25 nm 且停留 ≥ 40 ps | 两角都进入闭态窗口且停留 **≥ 200 ps** |
| 起点 | 展开态 | **开态 apo** |
| 初始化 | 10 ns | **20 ns** cMD（四种方法共用） |
| 短轨迹 | 1 ns × 6 seeds × 12 轮 | **2 ns × 6 seeds × 15 轮** |
| **每条总预算** | 82 ns | **200 ns**（20 + 180） |

力场仍是 AMBER99SB-ILDN + TIP3P，300 K，0.15 M NaCl，盒子缓冲 1.2 nm。  
开态盒子约 **63706 原子**，闭态约 **46500 原子**（闭态更紧凑）。  
晶体参考角：开态 LID 146° / NMP 36°，闭态 LID 106° / NMP 48°。闭态窗口写在 `systems/adk/angle_refs.json`。

## 命令（按顺序）

```bash
cd /home/ly/TAPS/moas-adk

# 1) pdb2gmx + 溶剂化 + 离子（CPU，约几分钟）
bash scripts/prepare_adk.sh

# 2) 开态 / 闭态 EM + 1 ns NVT + 1 ns NPT（GPU）
bash scripts/run_em_eq.sh

# 3) 开态 20 ns 无偏 cMD，作为自适应初始化
bash scripts/run_cmd_init.sh

# 4) 四种方法各一条 200 ns campaign（seed=0）。再加重复：SEED=1 bash scripts/run_discover.sh
bash scripts/run_discover.sh
```

分步等价命令：

```bash
python3 run_md.py --check
python3 run_md.py --system adk_open --length 0 --gpu --nt 16
python3 run_md.py --system adk_closed --length 0 --gpu --nt 16
python3 run_md.py --system adk_open --length 20 --gpu --nt 16
python3 stage_adk_discover.py --check
python3 stage_adk_discover.py --gpu --nt 16 --seed 0 --methods random last density moas \
  --init-ns 20 --budget-ns 200 --n-seeds 6 --short-ps 2000 --max-rounds 15
```

`run_md.py` 可续跑：同一条命令再执行会跳过已完成步骤，并从 `.cpt` 接着跑。

开态约 700 ns/day 时，每种方法新跑 180 ns 大约 **6 小时**；四种顺序跑完大约 **一天**。不要再把单条压回 80 ns 这一档，AdK 开–闭在那个长度上几乎看不出 committed 差异。

## 目录

```
moas-adk/
  systems/adk/structures/     4AKE / 1AKE 清洗 PDB
  systems/adk/gmx_common_*    pdb2gmx 后的蛋白
  systems/adk/water_open/     生产起点（溶剂化开态）
  systems/adk/water_closed/   闭态参考盒子
  systems/adk/angle_refs.json 开/闭角度与闭态窗口（prepare 后生成）
  stage_adk_discover.py       四方法自适应
  run_md.py                   EM / 平衡 / 生产
```

Campaign 标签：`adk_random`、`adk_last`、`adk_lc`、`adk_static`。

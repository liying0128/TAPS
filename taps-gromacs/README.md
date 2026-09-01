# TAPS GROMACS 实验文件夹

对应论文大纲：用短轨迹时序模型预测探索潜力，再选下一轮 MD 的 seed。  
本目录提供**主体系 + 扩展体系**的初始结构和可直接跑的 GROMACS 输入。本机已验证：`gmx` 2025.1、力场 `AMBER99SB-ILDN`、水模型 `TIP3P`。

> GROMACS 2025 已移除 GBSA 隐式溶剂。大纲中的“真空或隐式溶剂”在这里落实为：**真空大盒子 + 显式水** 两套。主体系建议先用真空把闭环跑通，再用显式水做正式对比。

---

## 体系与用途

| 体系 | 路径 | 角色 | 已准备内容 |
|---|---|---|---|
| 丙氨酸二肽 ACE-ALA-NME | `systems/alanine_dipeptide/` | **主体系**：消融、Ramachandran、机制分析 | 真空 + 显式水；C7eq / C7ax / C5 / αR 四个 seed |
| 丙氨酸四肽 ACE-(ALA)3-NME | `systems/alanine_tetrapeptide/` | 便宜的扩展 / 中间验证 | 真空 + 显式水；extended / helix |
| Chignolin CLN025 | `systems/chignolin_cln025/` | **扩展验证** | 显式水 + 0.15 M NaCl；native (5AWL)、NMR (2RVD)、unfolded |
| AdK | `systems/adk/` | 可选加分项 | 开态 4AKE、闭态 1AKE 清洗后的 chain A；溶剂化需额外命令 |

力场统一为 AMBER99SB-ILDN，便于体系间对比。CLN025 文献里常用 CHARMM22*，若以后要严格复现折叠时间，可再换力场；当前设置优先保证方法学闭环可跑。

---

## 推荐模拟参数（与大纲一致）

| 项目 | 主体系（二肽） | 扩展（CLN025） |
|---|---|---|
| 温度 | 300 K | 300 K（无偏） |
| 平衡 | NVT 1 ns（水体系再加 NPT 1 ns） | 同左 |
| **生产段（论文主线）** | **100 / 200 / 500 ns**（`--length`，默认 100 ns） | 同左；采样不够再加长 |
| 轨迹输出 | 真空 1 ps / 帧；水 10 ps / 帧 | 10 ps / 帧 |
| 自适应短轨迹 | 100 ps 或 500 ps（`--short`，给以后的 TAPS 闭环） | 500 ps–1 ns |
| 积分 | 2 fs，LINCS 约束氢 |

长轨迹是无偏 cMD 采样，用来把 Ramachandran / 覆盖率先跑够。自适应采样的“短轮次”仍然是 100–500 ps，不要把每轮都开成 100 ns。

自适应采样重启：`md_short*.mdp` 已设 `gen-vel = yes`，从选中的 seed gro 重新发速度。

---

## 目录结构

```
taps-gromacs/
  shared/mdp/                 全部 MDP 模板
  scripts/
    build_structures.py       生成/清洗 PDB
    prepare_gromacs.sh        pdb2gmx + 盒子 + 溶剂/离子
    run_em_eq.sh              能量最小化（可选预平衡）
    run_short_md.sh           跑一条短轨迹
    make_dihedral_index.py    生成 phi/psi 索引
  systems/<name>/
    structures/               初始 PDB / gro
    vacuum/  或  water/       拓扑、盒子、MDP、最小化后坐标
```

每个已溶剂化体系的关键文件：

- `topol.top` 拓扑  
- `ions.gro` 溶剂化并中和后的坐标（真空体系则是 `box.gro`）  
- `em.gro` 最小化后的可发枪结构（运行 `run_em_eq.sh` 后生成）  
- `mdp/` 该体系对应的 MDP  

---

## 一键运行（推荐，拷到服务器后用这个）

入口脚本根据 **脚本所在目录** 解析路径，不依赖本机绝对路径，也不依赖你从哪个目录启动。启动后会先在 Python 里检查解释器、可选包、GROMACS 和输入文件。

**跑 MD 本身不需要 pip 安装任何包**（标准库即可）。`numpy` / `scipy` / `torch` 是以后 TAPS 模型用的，缺了只会警告，不会拦住 GROMACS。

```bash
cd /path/to/taps-gromacs          # 任意拷贝后的位置

# 1) 先检查：Python 包、gmx、GPU、输入文件。不跑模拟。
python3 run_md.py --check

# 2) 论文主线：EM → 1 ns 平衡 → 100 ns 生产（检测到 4090 会自动开 GPU）
python3 run_md.py --system ala2_vacuum --nt 16 --length 100

# 需要更长采样时
python3 run_md.py --system ala2_vacuum --nt 16 --length 200
python3 run_md.py --system ala2_vacuum --nt 16 --length 500
```

建议先只跑主体系真空二肽；确认稳定后再加水和扩展体系：

```bash
python3 run_md.py --system ala2_water --nt 16 --length 100
python3 run_md.py --system ala4_vacuum --system cln025_water --nt 16 --length 100
```

其它常用开关：

```bash
python3 run_md.py --check --system ala2_vacuum
python3 run_md.py --cpu                      # 强制不用 GPU
python3 run_md.py --gpu                      # 强制 GPU（默认已是自动检测）
python3 run_md.py --short                    # 额外跑 100 ps，给以后的 TAPS 短轮次测试
python3 run_md.py --force                    # 忽略已完成结果，全量重跑
```

中断后用**同一条命令**再跑：已完成的步骤会跳过；未写完的 `mdrun` 从 `.cpt` 续跑。`--length 100/200/500` 写到不同文件（`runs/md_100ns` 等），不会互相覆盖。进度写在 `logs/run_state.json`。

可选体系：`ala2_vacuum` `ala2_water` `ala4_vacuum` `ala4_water` `cln025_water`（`python3 run_md.py --list`）。AdK 需先溶剂化再 `--adk`。不写 `--system` 时会按默认跑全部主体系，每个都是 100 ns，水体系会很久，服务器上请显式指定体系。

---

## 从零复现 / 重新生成


```bash
cd taps-gromacs
python3 scripts/build_structures.py
bash scripts/prepare_gromacs.sh
bash scripts/run_em_eq.sh                 # 只做 EM
# DO_EQ=1 bash scripts/run_em_eq.sh       # EM + 100 ps NVT/NPT

# 可选：溶剂化 AdK（体系大，默认跳过）
INCLUDE_ADK=1 bash scripts/prepare_gromacs.sh
```

---

## 跑通第一条短轨迹（主体系）

真空（最快，适合先搭 TAPS 闭环）：

```bash
bash scripts/run_short_md.sh \
  systems/alanine_dipeptide/vacuum em.gro md_short_vacuum.mdp run01
```

显式水（正式实验，需先完成 NPT；或先 `DO_EQ=1`）：

```bash
bash scripts/run_short_md.sh \
  systems/alanine_dipeptide/water npt.gro md_short.mdp run01
```

从其他 basin 发枪（真空）：

```bash
bash scripts/run_short_md.sh \
  systems/alanine_dipeptide/vacuum seeds/c7ax.gro md_short_vacuum.mdp c7ax_r1
```

---

## 二面角分析

```bash
python3 scripts/make_dihedral_index.py \
  systems/alanine_dipeptide/vacuum/em.gro \
  systems/alanine_dipeptide/vacuum/dihe.ndx

# phi = ACE-C, ALA-N, ALA-CA, ALA-C
# psi = ALA-N, ALA-CA, ALA-C, NME-N
gmx angle -f runs/run01.xtc -n dihe.ndx -ov phi.xvg -type dihedral
```

对二肽，原子序号在当前拓扑中固定为：

- **phi**: 5 7 9 15  
- **psi**: 7 9 15 17  

---

## 初始结构说明

**丙氨酸二肽**（构建后经 OpenMM 扭转约束最小化，再交 GROMACS `pdb2gmx -ignh`）：

| 文件 | 目标 basin（°） |
|---|---|
| `ala2_c7eq.pdb` | φ≈−80, ψ≈70（默认主 seed） |
| `ala2_c7ax.pdb` | φ≈70, ψ≈−70 |
| `ala2_c5.pdb` | φ≈−150, ψ≈150 |
| `ala2_alphaR.pdb` | φ≈−70, ψ≈−30 |

**Chignolin CLN025**（序列 YYDPETGTWY，两端为 NH3+/COO−）：

- `cln025_native.pdb`：晶体 5AWL chain A（折叠起点）  
- `cln025_nmr.pdb`：2RVD model 1  
- `cln025_unfolded.pdb`：伸展构象（折叠实验的起点）  

**AdK**：`adk_open.pdb`（4AKE-A）、`adk_closed.pdb`（1AKE-A，已去配体）。HIS 默认写成 HIE，避免 `pdb2gmx` 交互选择。

---

## 与 TAPS 闭环的衔接

1. 用本目录的平衡后结构作为第 0 轮 seed；论文主线先跑 `--length 100`（或 200/500）无偏生产轨迹，把采样跑够。  
2. 以后每轮并行多条 `md_short*.mdp` 短轨迹（`--short`），不要把自适应轮次也开成 100 ns。  
3. 从 xtc 抽帧 → 算密度与探索潜力 → 选 seed → 将该帧 `trjconv` 成 gro，再次调用 `run_short_md.sh`。  
4. 真空二肽用于方法开发；显式水二肽 + CLN025 用于正文结果。

物理合理性过滤（能量/碰撞惩罚）在选 seed 时做，不改这些 MDP 里的无偏动力学。

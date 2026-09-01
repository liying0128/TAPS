# 论文思路大纲：基于轨迹时序建模的探索潜力预测自适应采样

> 本大纲综合两套方案：保留“时空轨迹建模 + 物理合理性约束”的方法叙事，同时按可完成、可投稿的证据链控制体系体量与写作顺序。

---

## 0. 定位与原则

**方法名（暂定）：** TAPS（Trajectory-Aware Potential Sampling）

**一句话主张：**  
现有自适应采样多基于静态结构或全局奖励选 seed，无法利用短轨迹中的局部动力学信号。TAPS 从轨迹片段预测构象的**未来探索潜力**，再与相空间密度、物理合理性约束复合选 seed，在保持无偏采样的前提下加速构象空间覆盖与自由能收敛。

**写作原则（必须同时满足）：**

1. **前瞻性**：seed 选择利用时序动力学，而不只是当前帧的几何/密度。
2. **物理合理性**：抑制非物理 outlier，降低模拟崩溃，避免“低密度但即将炸掉”的构象。
3. **可完成性**：主体系把方法学做透，扩展体系证明可迁移；更大体系作为加分项而非硬门槛。
4. **可解释性**：用可视化与物理量关联证明模型学到的是“即将转移/高扩散”信号，而不是黑盒加速。

---

## 1. 建议题目

**英文：**  
Trajectory-Aware Adaptive Sampling for Molecular Dynamics: Predicting Dynamic Exploration Potential via Spatiotemporal Transformers

**中文：**  
基于时空轨迹 Transformer 预测动力学探索潜力的自适应分子动力学采样

备选更短标题：  
*Trajectory-Aware Potential Sampling (TAPS): Forward-Looking Seed Selection for Adaptive MD*

---

## 2. 体系选择策略

不要把全文做成“三个大体系都打满”的工程竞赛，也不要只停在 toy system。

| 层级 | 体系 | 作用 | 是否必须 |
|---|---|---|---|
| 主体系 | Alanine dipeptide（真空或隐式溶剂） | 方法开发、消融、机制分析、与 LAST/REAP 等直接对比 | **必须** |
| 扩展验证 | Chignolin (CLN025) 或 alanine tetrapeptide | 证明在稍复杂折叠/构象空间上仍有效 | **必须（择一）** |
| 加分项 | AdK（轻量设置，或仅展示路径探索） | 展示向大尺度构象转变的可扩展性 | 资源允许再做；不作为录用硬条件 |

**理由：**  
丙氨酸二肽计算快、自由能面已知、便于机制可视化；但完整研究论文需要可扩展性。Chignolin 足以承担“不是只能在 toy 上工作”的证明。AdK 叙事强，但计算与调参成本高，适合放在讨论/展望或 SI，避免拖死主线。

---

## 3. Abstract（约 200–250 词，写作骨架）

**背景：**  
MD 受稀有事件与高能垒限制。自适应采样通过“模拟–选择–重启”加速探索，但代表性方法存在两类缺陷：  
- LAST / VAE / PCA 等依赖**静态结构或边界密度**，无法区分“即将逃逸”与“死锁在阱中”；  
- Least-counts 等纯低密度策略容易选到非物理 outlier，导致模拟崩溃。  
REAP 等强化学习方法依赖全局奖励，前瞻性与可解释性有限。

**方法：**  
提出 TAPS。将短轨迹切片为时空序列，用空间编码器（GNN/MLP）+ 时间 Transformer（或 Temporal GNN）学习局部动力学（逃逸前兆、局部扩散），输出探索潜力分数 \(S_p(x)\)。选 seed 时复合三项信息：低密度边界、高探索潜力、物理合理性惩罚；并施加构象多样性约束。

**结果（写作时填数）：**  
在丙氨酸二肽上显著加速 Ramachandran 覆盖与 MSM 收敛，且崩溃率低于纯密度方法；在 Chignolin（或选定扩展体系）上验证可迁移性。消融表明时序信息与物理约束均不可缺。

**结论：**  
首次将轨迹时序动力学显式用于前瞻性、物理合理的 seed 选择，形成可在线更新的无偏自适应采样闭环。

---

## 4. Introduction

### 4.1 问题

- 稀有事件与时间尺度瓶颈。
- 自适应采样的优势：无偏、可并行、不依赖预定义 CV 增强。

### 4.2 现有策略的共同局限

按“缺了什么信息”来组织，而不是堆文献：

| 类型 | 代表 | 局限 |
|---|---|---|
| 静态结构 / 隐空间边界 | LAST、VAE/CVAE、DeepDriveMD | 丢失动量与局部动力学，分不清“准备逃逸”还是“几何异常” |
| 纯密度 / 计数 | Least-counts、metric-free | 盲目冲低密度区，易选非物理点 |
| 全局奖励 / 策略学习 | REAP、MA-REAP、AdaptiveBandit | 奖励定义难泛化，可解释性弱 |

共同缺口：**没有把短轨迹的时序演化当作选 seed 的一等特征。**

### 4.3 本文贡献（四条，对应后文实验）

1. **视角：** 从“静态单帧筛选”转向“轨迹片段的前瞻性预测”。
2. **模型：** 时空轨迹网络输出探索潜力分数 \(S_p\)；用辅助任务（next-frame / contrastive / 未来相空间扩展）监督局部动力学表征。
3. **决策：** 密度 + 潜力 + 物理惩罚的复合选 seed，并控制多样性，兼顾探索与稳定性。
4. **验证：** 在主体系上完成系统对比与消融；在扩展体系上证明可迁移；用可视化与物理量（扩散率、滞留时间、committor 近似）解释模型。

文末用一段话概述论文结构。

---

## 5. Methods

### 5.1 总体闭环

```
并行短 MD
    → 轨迹切片（窗口长度 T）
    → 时序模型评估 S_p
    → 密度估计 ρ(x) + 物理惩罚 E_penalty
    → 多样性约束下选 seed
    → 重启新一轮 MD
    → 在线更新模型
```

强调：**无额外偏置力**，加速来自重启位置的选择，而不是改变动力学本身。

### 5.2 轨迹表示

输入不绑死为坐标一种形式，主体系优先可解释、扩展体系再加重表示：

- 主体系：二面角 \((\phi,\psi)\) 或重原子坐标。
- 扩展体系：坐标 / 局部描述符 / 可选接触图。
- 统一写成窗口 \(\mathbf{X}_{t:t+T}\)。content1 的时空张量 \(\mathbf{X}\in\mathbb{R}^{T\times N\times 3}\) 作为通用形式；二肽上可退化为低维 CV 序列以便机制分析。

### 5.3 时空模型与潜力分数

**架构：**

- 空间编码：GNN 或 MLP，提取单帧结构。
- 时间编码：Temporal Transformer / Multi-Head Attention（或 Temporal GNN），提取帧间动量、扩散与逃逸前兆。

**\(S_p(x)\) 的操作定义（必须写死，避免空泛）：**  
该构象（或其所属短片段）在重启后到达**尚未充分采样的低密度区域**的预期能力。可用以下可计算代理之一（正文选一个主任务，其余放消融/SI）：

- 预测未来 \(M\) 步后的隐空间/CV 空间位移或离散度；
- 预测到达新低密度区的概率 / 预期信息增益；
- 对比学习：将“随后发生明显相空间扩展”的片段与“长时间滞留”的片段分开。

**训练：** 损失函数、优化器、窗口 \(T\)、在线更新频率。每轮新轨迹加入后微调，避免离线一次训练后失效。

### 5.4 复合 Seed 选择

综合两套方案：content1 的三项约束 + content2 的乘性/加权灵活性与多样性。

推荐主公式（正文可再校准权重形式）：

\[
\mathrm{Score}(x)
= \underbrace{S_p(x)}_{\text{前瞻潜力}}
\cdot
\underbrace{f\!\left(\frac{1}{\rho(x)}\right)}_{\text{低密度边界}}
- \underbrace{\lambda\, E_{\mathrm{penalty}}(x)}_{\text{物理合理性}}
\]

- \(\rho(x)\)：低维投影（PCA/TICA）或潜空间上的 KNN / KDE。
- \(f(1/\rho)\)：鼓励边界探索，但必须被 \(S_p\) 门控，避免纯 outlier。
- \(E_{\mathrm{penalty}}\)：高能、立体碰撞、极端键角等；用于压低崩溃构象。
- **多样性：** pairwise RMSD（或 CV 距离）阈值，避免同一阱内重复发枪。

消融时拆成四种策略：纯密度、纯潜力、密度+潜力、完整（再加惩罚与多样性）。

### 5.5 模拟与分析设置

必须在正文或 SI 写清，保证可复现：

- 引擎与力场（OpenMM / GROMACS）、温度、溶剂模型、短轨迹长度、并行数、总模拟预算对齐。
- **基线：** cMD、Least-counts、SDS、LAST；能复现则加 REAP。
- **指标：**
  - 构象覆盖速度（Ramachandran / PCA / TICA 面积、RMSD 分布）；
  - 目标态首次到达时间（FPT）；
  - MSM 质量（implied timescales、CK 检验、隐状态稳定性）；
  - 计算效率（相同总模拟时间下的覆盖/收敛）；
  - **模拟崩溃率**（继承 content1，用来证明物理约束有用）。

### 5.6 体系与计算预算

- 主体系：Alanine dipeptide，详细到足以支撑全部消融。
- 扩展体系：Chignolin 或 alanine tetrapeptide，重复**主要指标**（不必重复全部消融）。
- AdK：可选；若做，聚焦路径探索与是否避开局部陷阱，不与主体系抢篇幅。

---

## 6. Results and Discussion

写作顺序按**证据链**，不要一上来堆大体系加速倍数。

### 6.1 模型是否学到了动力学信号（主体系）

- 潜力分数在 Ramachandran 图上的分布：是否落在已知转移走廊，而非单纯几何 outlier。
- 被选 seed 的局部轨迹特征：即将跨越 vs 阱底振荡。
- 与物理量的相关：局部扩散率、滞留时间、committor 近似。
- **这一节是 novelty 的证明，不能省。**

### 6.2 自适应采样是否真的更快、更稳（主体系）

- 多轮后覆盖对比图（相同总时间）。
- C7eq → C7ax 等能垒跨越的迭代轮数 / FPT。
- MSM 收敛对比。
- 崩溃率：相对 Least-counts / 纯边界方法应明显下降。
- 定量表格：覆盖、FPT、MSM、效率、崩溃率。突出相对 LAST 的“前瞻性”优势。

### 6.3 消融与超参（主体系，可部分放 SI）

必须回答三个问题：

1. 时序模块是否必要？（替换为静态单帧 GNN/VAE）
2. \(S_p\) 与密度如何配权？（纯边界 vs 纯潜力 vs 复合）
3. 物理惩罚与多样性是否降低崩溃且不明显损害探索？

### 6.4 扩展体系上的可迁移性

在 Chignolin（或选定体系）上重复：覆盖/折叠到达、FEL 或 MSM 质量、相对 cMD 与 LAST 的加速、计算开销。  
讨论尺度增大后窗口长度、特征选择、在线更新的变化。不必强求 AdK；若有初步结果，作为 6.5 或 SI。

### 6.5 局限性

- 更大体系、显式溶剂、与 MSM 的更深度耦合仍待验证。
- \(S_p\) 的代理任务是“探索能力”而非严格动力学传播算符。
- 权重 \(\lambda\) 与窗口 \(T\) 需要一定体系相关校准。

---

## 7. Conclusion

- 时序动力学预测把自适应采样从“静态找边界”推进到“前瞻性选活跃边界”。
- 密度、潜力、物理约束三者缺一不可：只追低密度会崩，只追潜力可能困在局部活跃区。
- 展望：配体结合 / \(k_{\mathrm{off}}\)、膜蛋白变构、与 MSM 或 committor 学习结合；公开代码与可复现脚本。

---

## 8. Supporting Information（投稿时必备）

- 全部超参（模型、MD、选 seed 权重）。
- 额外投影图、更多随机种子的重复实验。
- 完整消融表。
- 代码可用性（GitHub）与复现说明。
- 若有 AdK 初步结果，优先放 SI，避免正文头重脚轻。

---

## 9. 实施顺序（先做后写）

1. **先跑通主体系闭环（优先 1–2 周量级）：**  
   OpenMM/GROMACS 短轨迹 → 简易 Temporal Transformer → 密度+潜力选 seed → 自动重启。先证明比 cMD / Least-counts / LAST 有可见优势。
2. **立刻补两块“能把文章撑起来”的证据：**  
   （a）时序 vs 静态消融；  
   （b）潜力分可视化 + 与转移区域/扩散率的对应。
3. **加上物理惩罚与崩溃率统计**，形成对纯密度方法的差异化。
4. **优势稳定后再上扩展体系**（Chignolin 或 tetrapeptide）。不要并行铺 AdK。
5. **写作时保持无偏采样叙事**，所有加速都来自 seed 选择，便于审稿人接受。

---

## 10. 相对两份原稿：本大纲保留了什么

| 来源 | 保留的优点 | 落在何处 |
|---|---|---|
| content1 | 时空模型（空间+时间）拆分 | Methods 5.3 |
| content1 | 逃逸 vs 死锁、非物理崩溃这两类痛点 | Intro + Abstract |
| content1 | 能量/碰撞惩罚与崩溃率指标 | 选 seed + 评价指标 |
| content1 | 复合分数与“边界但活跃”的决策叙事 | Methods 5.4 |
| content2 | 主体系 + 一个扩展的体量控制 | 第 2 节 |
| content2 | 先证模型、再证采样、再证迁移的证据链 | Results 6.1–6.4 |
| content2 | 方法命名、无偏采样、可复现设置与基线清单 | Abstract / Methods 5.5 |
| content2 | 多样性约束、物理量关联、SI 与开源 | 5.4 / 6.1 / 第 8–9 节 |

**刻意降权：** 把 AdK 从“第三套必须 benchmark”改为可选加分项，以免方法学主线被计算量绑死。



8.23
深入挖掘 CLN025 的时序前瞻特征问题：TAPS 比 LAST 早 8 ns 触碰折叠态，说明它确实在早期具备某种推动构象跨越的能力。解法：详细分析 TAPS 在 0–30.5 ns 期间选出的种子轨迹，对比 LAST 在相同时间段选出的种子。检查 TAPS 的短轨迹是否提前预测到了主链二面角或氢键形成的微观动作（例如 Turn 结构的形成）。如果是，说明 Transformer 确实看到了“隐空间边界看不见的微观弛豫趋势”，这可以作为支撑 Claim 的有力 Case Study。

核心原则是：不再试图证明纯 TAPS 全面优于 LAST，而是利用前期实验揭示的互补性，设计并验证一个阶段自适应/不确定性感知的混合采样框架。

后续研究与实验设计总纲：从 TAPS 到 Stage-Adaptive Hybrid Sampling
一、研究目标与核心假设
1.1 当前研究发现

现有 alanine dipeptide 和 CLN025 结果表明：

自适应采样整体优于同预算裸 cMD，但这一点本身不是新的核心贡献。
LAST / density-boundary 方法在早期构象空间拓展、低密度区域发现以及后续稳定 basin 的开采方面具有明显优势。
TAPS 可以利用短轨迹中的局部动力学信息，在部分场景下具有不同于纯静态 density/latent-space 方法的 seed ranking 行为，但其前期预测并不稳定。
alanine dipeptide 中，TAPS 未能从 C7eq 一侧真正发现 C7ax；注入 C7ax 后，TAPS 对已知稀有 basin 的再探索能力有所增强。
CLN025 中 TAPS 30.54 ns 的 RMSD<0.25 nm 事件只是单帧 transient crossing，并不能证明 TAPS 识别到了 folding precursor；LAST 虽然首次跨越稍晚，但后续 folded-basin residence 和重复 exploitation 明显更强。
当前 S_p 与 seed RMSD、未来 RMSD 下降幅度高度相关，说明现有模型容易学习“展开程度→未来 RMSD 有下降空间”的 shortcut，而不是可靠的 folding precursor。
因此，目前没有证据支持“纯 TAPS 在所有阶段优于 LAST”或“trajectory temporal information 能系统性发现 LAST 看不到的微观前兆”。
1.2 新的核心假设

提出新的 stage-adaptive hybrid sampling hypothesis：

不同自适应采样策略在构象探索的不同阶段具有互补优势。早期采样更需要基于 density / boundary / diversity 的全局空间探索；当构象空间逐渐饱和后，短轨迹历史可能提供额外的局部动力学信息，用于预测候选 seed 的未来探索价值。因此，通过动态融合 LAST-style structural novelty 与 trajectory-based future utility，可以获得比任一单一策略更高的单位计算预算有效探索效率。

核心不是证明：

TAPS > LAST

而是验证：

Hybrid(TAPS + LAST) > LAST

以及：

Hybrid(TAPS + LAST) > TAPS

二、第一阶段：离线分析现有轨迹，证明两类策略存在互补性

在新增大量 MD 之前完成。

2.1 建立统一的候选 seed 数据集

从现有：

alanine dipeptide
CLN025
cMD trajectories
LAST trajectories
Least-counts trajectories
TAPS trajectories

中提取所有可能的 candidate seed。

每个 seed 保存：

Static features
RMSD
radius of gyration
local density
distance to known clusters
latent-space coordinates
LAST score
Least-counts score
diversity score
Temporal features

从 seed 前的 50/100/200 ps trajectory window 提取：

coordinate/internal-coordinate changes
RMSD velocity
RMSD acceleration
local MSD
local diffusion coefficient
displacement variance
directional persistence
contact formation/breaking
hydrogen-bond formation/breaking
secondary-structure changes
distance/contact fluctuations
latent-space velocity
latent-space acceleration
local density change
transition frequency
三、重新定义 Future Utility，而不是继续使用简单的 RMSD escape label
3.1 废弃当前简单目标

不要再把：

future RMSD decrease

作为主要 prediction target。

也不要使用：

binary escape / no escape

作为主要标签。

原因：

容易受到初始 RMSD 的强烈影响；
容易把普通 fluctuation 当成 exploration；
不能区分 transient hit 与真正 basin discovery；
不能反映后续 residence / commitment。
3.2 建立 Future Exploration Utility（FEU）

对每个 candidate seed，在未来固定 horizon，例如：

200 ps
500 ps
1 ns

计算真实 future utility。

建议至少包含四个维度：

A. Future novelty

未来 trajectory 是否进入当前采样空间中的低密度/未充分采样区域。

B. Future diversity

未来 trajectory 产生多少新的 cluster / bins / latent states。

C. Basin discovery

是否进入新的 metastable basin 或目标构象区域。

D. Commitment / persistence

进入新区域后是否能够持续停留，而不是只产生单帧 crossing。

例如定义：

minimum residence time
consecutive-frame count
probability of remaining in basin
return probability
3.3 构建综合 Future Utility Score

例如：

FEU = w1 × Novelty + w2 × Diversity + w3 × BasinDiscovery + w4 × Commitment

同时保留每个 component，避免只报告一个黑箱综合分数。

需要测试不同权重方案：

equal weighting
normalized weighting
validation-set optimized weighting
四、第二阶段：验证“时序信息到底有没有增量价值”

建立严格的 ablation hierarchy。

4.1 Model A：Last-frame baseline

只输入：

x_t

预测 FEU。

4.2 Model B：Static feature model

输入：

RMSD
Rg
density
latent coordinates
diversity
structural descriptors

预测 FEU。

4.3 Model C：Trajectory-statistics model

输入：

MSD
diffusion
velocity
acceleration
contact dynamics
H-bond dynamics
latent-space movement

预测 FEU。

4.4 Model D：Temporal neural network

比较：

GRU/LSTM
Temporal CNN
Transformer

输入完整 short trajectory。

4.5 必须报告
MSE / MAE
Spearman correlation
Pearson correlation
top-k ranking precision
top 10% seed enrichment
calibration
uncertainty calibration

最重要的不是单纯 prediction MSE，而是：

模型能否正确把真正 high-FEU seed 排到前面。

五、第三阶段：确定 TAPS 什么时候值得被信任

建立模型 uncertainty。

推荐至少比较：

ensemble models
MC dropout
bootstrap ensemble

对于每个 seed 输出：

μ_TAPS = predicted FEU

σ_TAPS = predictive uncertainty

定义：

confidence = function(μ_TAPS, σ_TAPS)

验证：

TAPS uncertainty 是否能够预测模型 ranking 的可靠性。

例如比较：

low uncertainty seeds 的实际 FEU
high uncertainty seeds 的实际 FEU

如果 uncertainty 没有 calibration value，则放弃 uncertainty controller，采用简单 stage-based controller。

六、第四阶段：定量分析 LAST 与 TAPS 的互补性

这是整个混合策略成立的关键实验。

对于每个 sampling round，计算：

LAST ranking

R_LAST

TAPS ranking

R_TAPS

然后比较：

Spearman correlation
top-k overlap
Jaccard similarity
rank disagreement
each method's top-ranked seed 的真实 future utility

重点回答：

LAST 和 TAPS 是否在不同 sampling stage 选择不同类型的 seed？

6.1 按 sampling stage 分析

把采样过程划分为：

Early stage

构象空间尚未充分覆盖。

Middle stage

coverage 增长开始减慢。

Late stage

global coverage 接近 saturation，主要进行局部 refinement / basin exploitation。

分别计算：

Performance(LAST, stage)

Performance(TAPS, stage)

预期需要验证：

LAST early-stage 更强；
TAPS 在部分 middle/late-stage 指标上提供增量；
两者具有互补性。

注意：这是需要实验验证的假设，不允许预先写成结论。

七、第五阶段：建立最简单的 Hybrid Sampling baseline

先不要直接做复杂 controller。

设计固定阶段切换：

Hybrid-1

前 25% budget：

LAST

后 75%：

TAPS

Hybrid-2

前 50%：

LAST

后 50%：

TAPS

Hybrid-3

前 75%：

LAST

后 25%：

TAPS

并比较：

cMD
Least-counts
LAST
TAPS
Hybrid-1
Hybrid-2
Hybrid-3

这样可以先判断：

“先 LAST、后 TAPS”这个最基本思想是否成立。

八、第六阶段：建立基于 coverage saturation 的动态切换

固定轮次切换如果有效，再进一步取消固定时间点。

定义：

CoverageGain_t = ΔCoverage / ΔBudget

监测最近 N 个 sampling rounds。

当：

CoverageGain_t < threshold

持续若干轮时，认为：

global exploration 开始饱和。

此时增加 TAPS 权重。

形成：

LAST → Hybrid → TAPS

而不是固定：

LAST → TAPS

九、第七阶段：建立 uncertainty-aware Hybrid Controller

最终方法设计为：

Score_i(t) = w_L(t) × S_LAST(i) + w_T(t) × S_TAPS(i)

其中：

w_L(t) + w_T(t) = 1

9.1 Controller 输入

至少包括：

current coverage
recent coverage gain
density saturation
TAPS predictive uncertainty
recent TAPS ranking performance
recent productive discovery rate
diversity saturation
9.2 Controller 行为
Early stage

coverage low：

w_LAST → 1

主要依赖 LAST / density-boundary。

Middle stage

coverage 开始饱和：

w_TAPS ↑

进入 hybrid regime。

Late stage

如果：

TAPS uncertainty low
recent predictive gain high
productive discovery rate high

则：

w_TAPS → 1

否则保持 hybrid，而不是强制切换到 TAPS。

十、第八阶段：定义“productive exploration”，替代单纯 first-hit 指标

最终 benchmark 不应该只报告：

Time to first RMSD < threshold

需要至少增加：

10.1 Coverage

构象空间覆盖率。

10.2 Novel-state discovery

单位计算预算发现的新 cluster / state 数量。

10.3 Committed discovery

首次进入目标 basin 并持续：

τ_commit

以上的时间。

10.4 Residence

新 basin 的 residence time。

10.5 Re-exploitation

发现新 basin 后，后续 restart 是否能够再次访问并进一步开采。

10.6 Information gain

例如：

conformational entropy gain
FEL coverage gain
MSM state discovery
uncertainty reduction
10.7 Efficiency

统一计算：

useful discoveries / ns

或者：

information gain / GPU-hour

最终重点指标：

productive exploration per unit simulation budget

十一、第九阶段：CLN025 重新分析

现有 CLN025 的 30.54 ns transient RMSD crossing 不再作为 TAPS superiority case。

重新定义：

Discovery

是否第一次进入 folded-like region。

Commitment

是否保持 folded state ≥ τ。

Re-exploitation

后续是否能够反复从 folded basin 启动并继续采样。

重点比较：

cMD
Least-counts
LAST
TAPS
Hybrid

验证 Hybrid 是否同时获得：

LAST 的稳定 basin exploitation

和

TAPS 的 trajectory-conditioned local refinement。

十二、第十阶段：Alanine dipeptide 重新定位

Alanine dipeptide 不再承担“证明 TAPS 发现 C7ax”的任务。

主要用于：

12.1 Global exploration

比较各方法 Ramachandran coverage。

12.2 Rare-state discovery

严格禁止 C7ax seed 注入，测试真正 discovery。

12.3 Known rare-state exploitation

单独做 C7ax injection experiment，分析：

residence
return frequency
local exploration
positive-φ coverage

将 discovery 与 exploitation 明确分开。

12.4 Dynamic prediction

验证 trajectory history 对 future utility 是否有增量预测能力。

十三、第十一阶段：必须增加一个新的、更加适合验证 hybrid strategy 的体系

不要只依赖 alanine dipeptide + CLN025。

增加至少一个具有：

多个 metastable states
明显 kinetic barriers
非 trivial transition pathways
足够短时间内可以完成多轮 adaptive sampling

的体系。

优先考虑：

chignolin
alanine tetrapeptide
small peptide with multiple metastable conformations

如果计算资源允许，再增加一个更复杂体系。

十四、第十二阶段：最终方法对照矩阵

最终至少比较：

Method	Global exploration	Local dynamics	Basin commitment	Computational cost
cMD	baseline	—	baseline	low
Least-counts	✓	—	moderate	low
LAST	✓✓	limited	✓✓	moderate
TAPS	limited	✓✓	uncertain	moderate
Fixed Hybrid	✓✓	✓	✓	moderate
Stage-Adaptive Hybrid	✓✓	✓✓	✓✓	moderate
Uncertainty-Aware Hybrid	✓✓	✓✓	✓✓	moderate
十五、第十三阶段：必须做的消融实验

最终方法至少做：

Ablation 1

无 LAST：

TAPS only

Ablation 2

无 temporal component：

LAST only

Ablation 3

固定 switching：

Fixed Hybrid

Ablation 4

coverage-based switching：

Coverage Hybrid

Ablation 5

uncertainty-aware switching：

Uncertainty Hybrid

Ablation 6

无 commitment term。

Ablation 7

有 commitment term。

Ablation 8

不同 temporal window：

25 ps
50 ps
100 ps
200 ps
Ablation 9

不同 future horizon：

100 ps
200 ps
500 ps
1 ns
构想新颖程度的评价（修订，对应 hybrid07）

旧 §6.1 用 S_p 的 Ramachandran 分布、与局部扩散率相关、以及 first-hit 早于 LAST，作为“时序构想新颖”的证明。这套评价已经不够：

- S_p 容易学到 RMSD shortcut，看起来像动力学，其实是几何；
- first-hit 把单帧 transient crossing 当成发现；
- 与扩散率相关不能证明比 LAST 多看到了不同的高价值 seed。

改为八条可证伪门控（代码：`hybrid07_novelty_audit.py`）：

1. 扣掉 RMSD / 密度 / LAST 之后，时序残差仍能排序 FEU；
2. 完整模型必须明显优于 −RMSD shortcut；
3. TAPS 残差能找回 LAST top-k 之外的真高 FEU seed；
4. LAST 与 TAPS 的排名 Jaccard / Spearman 足够低（选的是不同点）；
5. 成功标准改为 first_commit / residence / re-exploitation，而不是 first-hit；
6. FEU 在 equal / commit / nocommit 权重下排序仍稳健，且 commitment 能改变排序；
7. novelty 改为 rare + entropy-gain + persist，能把“扫过空 bin 但停不住”的 flicker 降权；
8. 固定 LAST→TAPS 拼接若全面不优于 LAST，不得把 Hybrid>LAST 写成结论。

uncertainty 未校准则只允许 stage-based 切换，不允许把方法写成 uncertainty-aware。

十六、第十四阶段：最终 Go / No-Go 判据

整个研究必须设置明确的停止标准。

Go

只有当 Hybrid / SA-TAPS 满足：

相比 LAST，整体 productive exploration 有统计学改善；
相比 TAPS，早期 coverage 不明显下降；
improvement 不是由额外计算预算造成；
多个体系中趋势一致；
uncertainty / switching criterion 本身具有可解释性；
ablation 证明 hybrid component 真正贡献性能。

才继续作为核心方法论文。

No-Go

如果：

TAPS temporal prediction 仍无法超过 static baseline；
LAST + TAPS hybrid 不优于 LAST；
switching criterion 只是 heuristic；
improvement 只出现在单个体系；
improvement 主要来自增加模型复杂度；

则不要强行把 TAPS 包装成新方法，应转向：

systematic analysis of complementary adaptive sampling strategies

而不是继续堆模型。

十七、最终论文的方法学逻辑

最终希望形成：

最终核心科学问题

不要再定位为：

“Transformer 能不能比 LAST 更好地选 seed？”

而定位为：

“不同自适应采样策略是否具有阶段依赖的互补性，以及能否通过一个基于采样状态、轨迹预测能力和模型不确定性的动态控制器，在有限 MD 预算下实现更高效的 productive conformational exploration？”

这条路线最重要的一点是：你现在已经做的 TAPS 实验不是被推翻，而是变成 Hybrid 方法设计的“发现阶段（discovery/diagnosis phase）”。 先用已有数据证明“为什么单一策略不够”，再用 controlled experiments 证明“为什么组合策略有效”，最后才进入新的体系验证。这样整个研究逻辑会比单纯追求 TAPS 打败 LAST 扎实得多。
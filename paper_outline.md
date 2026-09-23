From Transient Encounters to Committed Sampling: A Multi-Objective Adaptive Sampling Strategy for Rare Protein Conformational States

核心思想：

不再把 first hit 作为 adaptive sampling 成功的主要标准，而是评价能否 committed 进入目标 basin，并持续占据该 basin。

1. Introduction
主要内容
蛋白质构象转变属于 rare-event sampling 问题。
Adaptive sampling 通过不断选择新的 seed 提高探索效率。
现有方法主要侧重：
random exploration
low-density exploration
boundary exploration
machine-learning-based exploration
First hit 并不等于成功采样：
可能只是瞬时进入 target window；
很快离开；
实际没有形成稳定 target-basin sampling。
因此提出：
committed visit
persistent target-basin occupancy
提出 MOAS：
Novelty
Boundary exploration
Target proximity
Diversity-constrained seed selection
Introduction 最后提出的核心假设

Effective adaptive sampling should balance exploration of poorly sampled conformational regions with target-directed exploitation, thereby converting transient target encounters into committed and persistent target-state sampling.

2. Methods
2.1 MOAS framework

介绍整体算法流程：

Initial MD
↓
Collect configurations
↓
Calculate multiple objectives
↓
Novelty + Boundary + Target proximity
↓
Rank candidate configurations
↓
Diversity-constrained seed selection
↓
Short MD
↓
Repeat
图

Fig. 1A–F：MOAS workflow

包括：

adaptive sampling 基本流程
三个 objective
candidate ranking
seed diversity selection
iterative sampling cycle
2.2 Objective functions

分别定义：

Novelty score
Boundary score
Target-proximity score

说明：

数学定义
normalization
weighting
diversity constraint
2.3 Benchmark systems

三个体系：

System	主要构象变化	CV
CLN025	folding	CA-RMSD + Rg
AdK	open → closed	LID/NMP angles
MBP	large-scale domain closure	domain distance + hinge angle
2.4 Baseline methods

统一比较：

Random
LAST
Least-counts
kNN-AS
MOAS-static

如果保留 TAPS，则作为 supplementary / additional comparison，而不是主线。

2.5 Evaluation criteria

这是文章的重要方法学部分。

三个指标：

① First hit

第一次进入 target window。

② Committed visit

达到预先定义的持续驻留标准。

③ Target-basin occupancy

整个模拟过程中 target basin 的占比。

强调：

Committed visit is the primary success criterion.

2.6 Statistical analysis

建议：

n = 3 independent replicates
Kaplan–Meier / time-to-event
median + IQR
bootstrap CI
effect size
replicate-level data
3. Results

只报告现象和数据，不在这里展开机制解释。主线三步：

first hit 不够 → MOAS 更容易 committed → 进入后 occupancy 更高。

Ablation 作为结果放在本节末尾，机制解读放到 Discussion。

3.1 First hit does not necessarily indicate successful sampling
要说什么

先不要急着证明 MOAS 最好。

先证明：

first hit 是一个不充分的评价指标。

重点案例：

TAPS：快速 first hit，但没有 committed
kNN-AS：能够 hit，但 occupancy 很低
LAST：可以 hit/commit，但 basin residence 较低
图
Fig. 2 — From first hit to committed sampling

建议包括：

A. 典型 trajectory：first hit → escape

B. first hit 与 committed visit 的区别

C. first-hit time vs target occupancy

D. 各方法 first hit → committed 的转换情况

这一张图建立全文的核心问题。

3.2 MOAS improves committed sampling across protein systems

把三个体系放在一起，不要写成三个完全独立的小故事。

要说什么

MOAS 在不同复杂度体系中：

committed success 更稳定；
target occupancy 更高；
不一定每次 first hit 最快；
但进入以后更容易真正留下来。
图
Fig. 3 — Cross-system benchmark

建议做成一个大 Figure：

A

CLN025 committed success

B

AdK committed success

C

MBP committed success

D

三体系 time-to-commit

E

三体系 target-basin occupancy

F

所有 replicate 的综合 heatmap / success matrix

重点突出：

MOAS：CLN025 3/3，AdK 3/3，MBP 3/3。

3.3 MOAS improves persistent target-basin exploration

这一节专门讲：

MOAS 的优势不仅是“找到”，而是“找到以后持续采样”。

图
Fig. 4 — Target-basin residence and occupancy
A

CLN025 occupancy

B

AdK occupancy

C

MBP occupancy

D

代表性 trajectory / CV landscape

E

first-hit time vs occupancy

这里重点突出：

CLN025：MOAS ≈ 4.8%
AdK：MOAS ≈ 15–28%
MBP：MOAS ≈ 28–42%

以及：

LAST / kNN-AS 可以探索甚至碰到目标，但 target-basin residence 明显不足。

3.4 Ablation and robustness analysis

这是为了让 reviewer 相信：

MOAS 的效果不是一个“碰巧有效的经验公式”。

必做

至少选择 AdK 或 MBP 一个体系做 ablation。

比较：

Novelty only
Boundary only
Target only
Novelty + Boundary
Novelty + Target
Boundary + Target
Full MOAS
图
Fig. 5 — Ablation of MOAS objectives
A

Committed success

B

Time-to-commit

C

Target occupancy

D

Objective contribution / performance summary

参数 robustness

可以放 SI：

objective weighting
number of selected seeds
diversity threshold
sampling rounds
SI Figures
S1：weight sensitivity
S2：seed-number sensitivity
S3：trajectory-level results
S4：parameter sensitivity

4. Discussion

解释结果，不重复罗列数字。两问：为什么 MOAS 有效？它和 exploration-oriented 方法分别优化什么？

4.1 Why does MOAS work?

这是冲 JCTC 最关键的一节之一。

要说什么

解释三个 objective 的功能：

Novelty
   ↓
避免重复探索

Boundary
   ↓
扩大构象空间覆盖

Target proximity
   ↓
把探索资源导向目标

三者结合
   ↓
Exploration → Transition → Exploitation

回扣 Results：

Fig. 2：为什么 first hit 会变成 transient encounter
Fig. 3–4：为什么 committed success 和 occupancy 会一起提高
Fig. 5：为什么缺一个 objective 就会偏 exploration 或偏 exploitation
图
Fig. 6 — Multi-objective seed-selection mechanism

建议：

A. 三 objective space

B. Random / LAST / kNN-AS 的 seed 分布

C. MOAS seed 分布

D. 不同 adaptive rounds 的 objective-space evolution

E. seed 从 early exploration → late target-directed exploitation 的变化

这一张图回答：

为什么 MOAS 有效？

4.2 Comparison with exploration-oriented adaptive sampling

专门讨论：

LAST
kNN-AS
Least-counts
核心观点

不是说：

“这些方法不好。”

而是：

它们和 MOAS 优化的是不同目标。

可以总结成：

LAST / kNN-AS
        ↓
exploration / boundary expansion

Least-counts
        ↓
density balancing

MOAS
        ↓
exploration
+
target-directed exploitation
        ↓
committed sampling
图

可以与 Fig. 6 合并，也可以放：

Fig. 7 — Exploration versus target-directed sampling

二维图：

X：exploration efficiency
Y：target-directed efficiency
点：Random / LAST / Least-counts / kNN-AS / MOAS

MOAS 应该体现出两者之间的平衡。

5. Conclusions

只保留三个核心结论：

①

First hit should not be treated as sufficient evidence of successful adaptive sampling.

②

MOAS combines novelty, boundary exploration, and target proximity to improve committed target-state discovery.

③

Across CLN025, AdK, and MBP, MOAS consistently improves both committed success and persistent target-basin occupancy.

最终主文 Figure 建议

如果控制在 6 张主图，按出现顺序：

Results
Figure	内容	作用
Fig. 1	MOAS 算法与三个 objective（Methods）	我提出了什么？
Fig. 2	First hit vs committed visit	为什么现有评价方式不够？
Fig. 3	CLN025 + AdK + MBP 综合 benchmark	MOAS 是否有效？
Fig. 4	target-basin occupancy / residence	MOAS 的真正优势是什么？
Fig. 5	ablation + robustness	是不是确实因为三个 objective？

Discussion
Figure	内容	作用
Fig. 6	objective-space + seed-selection mechanism	为什么有效？
Fig. 7（可选）	exploration vs target-directed	和其他方法优化的目标有何不同？

然后：

Supporting Information

S1 详细 simulation parameters
S2 所有 replicate trajectory
S3 First-hit 数据
S4 RMSD/CV trajectory
S5 kNN-AS 完整结果
S6 weighting sensitivity
S7 seed-number sensitivity
S8 diversity-constraint sensitivity
S9 其他 baseline / TAPS
最后把整篇文章压缩成一句话

Fig. 1：提出 MOAS → Fig. 2：证明 first hit 不等于成功 → Fig. 3：三个体系证明 MOAS 更容易 committed → Fig. 4：证明 MOAS 进入后真的待得更久 → Fig. 5：ablation 证明三个 objective 缺一不可 → Fig. 6：解释三个 objective 为什么互补。

这样整篇文章就不是：

“我们提出了一个新算法，而且它比 Random/LAST 好。”

而是：

“我们重新定义了 adaptive sampling 中‘成功发现目标态’的问题，并提出一个可解释的 multi-objective seed-selection framework，将构象空间 exploration 与 target-basin exploitation 结合起来，从而把 transient encounters 转化为 committed and persistent sampling。”
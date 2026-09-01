# AdK（可选加分体系）

清洗后的初始结构：

- `structures/adk_open.pdb`：开态，PDB 4AKE chain A
- `structures/adk_closed.pdb`：闭态，PDB 1AKE chain A（已去除 AP5A 配体）

`mdp/` 中已放入与其它体系相同的 AMBER99SB-ILDN / TIP3P 模板。

溶剂化（体系较大，默认未执行）：

```bash
INCLUDE_ADK=1 bash scripts/prepare_gromacs.sh
```

完成后会生成 `water_open/` 与 `water_closed/`（1.2 nm 缓冲、0.15 M NaCl）。
HIS 已写成 HIE，避免 pdb2gmx 交互选择。

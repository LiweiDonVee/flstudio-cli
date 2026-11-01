# Sytrus：从明确起点执行

## 真正的 init 合约

“加载了一个预设”和“已合成新音色”需要分别记录。工厂 **Default** 可以提供合法的插件容器，但只有明确检查并写入振荡器、矩阵、包络和效果，才能把它当作这次设计的初始化起点。不要从任意漂亮预设开始再声称从零合成。

以下是 UI 可执行的受控起点；若改为 state/API 执行，必须有本机版本的字段定位和读回。依据 P01/P02/C01。

1. 在独立工程副本中加载 Sytrus **Default**，保存新的基线与完整工程；记录插件/FL 版本及检查点路径。
2. MAIN：master pitch 为 0 半音，Unison order 为 1，输出 EQ 中性。停止使用 portamento/随机映射/LFO。FX 路由关闭，chorus order 为 0，三路 delay 禁用；不靠效果掩盖干音。
3. OP1：频率 offset 为 0 Hz，ratio 明确设为 **1.000**。官方手册中 ratio 默认是 **2**，因此不能把 Default 的键盘音高默认当成基频。其余算子的 ratio 也显式设置后再启用。
4. 将 OP1 波形 modifier 和谐波编辑器恢复至 sine 起点；检查 SH/TN/SK/SN/FL/NS，不只看 SH 一个滑杆。算子不处于 Pluck 模式。把可能导致每次触发不同的 phase/random 配置记录下来。
5. 分别检查 FM 和 RM 两个矩阵视图，清空算子间调制和反馈。两种矩阵可同时存在；切换 FM/RM 按钮只是切换编辑视图，不表示另一种调制已被清除。
6. 干音基线仅 OP1 → OUT 为 100%；OP2–6、F1–3 → OUT 为 0；所有 filter send/FX send 为 0。先确认这个单一路由有声。
7. OP1 的 VOL → ENV 显式启用。创建简单包络并检查 attack/decay/sustain/release 标记：A 5 ms、D 150 ms、S 70%、R 120 ms 是本库的测试起点，不是宿主整数值。保持 MIDI note-off 与尾音窗口明确。
8. 播放固定 CLI `Note.key`、velocity 和长度的音符，并测实际基频。本机真实 `Note.key=36`、master pitch/offset=0 时，ratio=1 主峰为65.441Hz，ratio=2为130.882Hz。不要混淆 MIDI、FL 显示八度与 CLI key。此为音高/路由检查，不是“好听”检查；记录静音、削波和尾音结果。

初始化检查不能只依赖 MAIN 的全局 ADSR：P01/P02/C01 都指出，它们是已存在/已启用的个体包络的全局调整；个体 ENV 没开或相关阶段/标记不存在时，滑动全局参数可能无效。

## 振荡器、谐波和音高

| 操作 | 已读到的机制 | 实际执行/预期 | 常见失败与替代 |
|---|---|---|---|
| Frequency Ratio / Offset | ratio 乘以键盘基频；offset 是绝对 Hz；默认 ratio=2（P01） | 从 ratio=1、offset=0 开始；ratio×2 提高八度 | 与 MAIN pitch、Piano roll 音名一起检查；不要把 offset 当 detune cents |
| SH 波形变形 | 官方教程以 Default 为起点，SH=50% 得到 saw；其余 modifier 会影响形状（P01/P02） | 先重置 modifier，再按官方步骤把 SH 设 50%；保存与 sine 的对照 | 若载入的起点不同，不保证 SH50%=saw；重新核对形状/谐波 |
| 谐波编辑 | 最多128个谐波；上行为振幅、下行为相位；振幅标尺为对数（P01） | 少量增减高次谐波，记录具体 harmonic 与显示值；先不改变相位 | UI50%不等于线性振幅0.5；不可直接从柱高猜振幅字节 |
| Convert shape to sine harmonics | 将现有形状转换为最接近的有限正弦谐波表示（P01/C01） | 需要可控谐波时转换，再逐条改谐波 | 不是无限精度重建；高音区必须检查混叠与原生导出 |
| Pluck | 谱逐渐衰减到基频正弦；DAMP 控制衰减（P01） | 用富谐波起点做拨弦候选 | sine 起点几乎无可衰减内容；Pluck 算子不接受 FM，其 FM 行禁用，RM仍可 |
| Declick / B.Limit / Center | 起音去点击、波形限带、DC移除是不同操作（P01/C01） | 独立检查点击、混叠、DC，不用一个开关代替另一项 | 遇到点击先核对起始相位与短 A；“更糙”不应由意外点击伪造 |

## 矩阵方向必须写成有向边

FM/RM 的左上算子区域：**列是源，行是被调制算子**。例如 OP1 行、OP2 列是 **OP2 → OP1**，不是反过来。对角线为自反馈。FM 与 RM 的深度均应保留独立状态。

Filter send 区域：F1 行、OP1 列是 **OP1 → F1**。最右 OUT 列：F1 行是 **F1 → OUT**。这两条都存在，滤波器才有输入和输出。官方教程特别演示了误把 OP2 送入 F1 时，听到的是未调制 OP2，而非已经被调制的 OP1（P02）。

| 目标 | 必要连线 | 必须关掉的旁路 |
|---|---|---|
| 干净单算子 | OP1→OUT=100% | 其他 OUT、全部 FM/RM、filter send、FX send |
| 两算子 FM | FM OP2→OP1；OP1→OUT | OP2→OUT=0%，避免把调制源额外混进音频 |
| 调制后再滤波 | FM OP2→OP1；OP1→F1=100%；F1→OUT=100% | OP1→OUT=0%，否则直接通路会掩盖滤波变化 |
| RM 比较 | 独立设置 RM OP2→OP1；OP1→OUT | 保持 FM 矩阵为0，先分别验证，再考虑叠加 |

矩阵负值会反转调制相位/发送极性；不等于“更少亮度”。P01 说明矩阵旋钮不能直接自动化，而算子的 **VOL** 可自动化并可控制该源对其他算子的调制强度。由此用 OP2 VOL→ENV 构造“起音强、随后弱”的 FM 深度，比误把 OP1 的音量包络当作 FM 亮度包络更明确。

## 两个最小实验

**FM 亮度候选**：使用上面的 sine 干音起点。OP2 sine、ratio=2.000、offset=0、OP2→OUT=0；FM OP2→OP1 依次为0%、10%、25%。先保持持续音量和演奏一致，再匹配输出响度。预期是增加边带、改变波形与亮度/质感；深度不是单调审美评分。下一轮只启用 OP2 VOL→ENV 的快速衰减，观察音色是否从较复杂的起音回到较简单的持续段。若变得刺耳或音高模糊，先减 FM 深度或把比例改回较简单的整数关系。来源 P01/P02/C04/C05；具体10%/25%为本库起点。

**滤波包络候选**：OP1 saw（已重置其它 modifier、SH50%）；OP1→OUT=0、OP1→F1=100%、F1→OUT=100%；FILT1选低通。先让 CUT→ENV 关闭，扫静态 cutoff，证明路由有效；然后显式启用 CUT→ENV，再修改 A/D/S/R。若没有变化，按“输入路由 → 输出路由 → 直接旁路 → filter类型 → cutoff → ENV LED → 包络深度/标记”顺序排查。不要靠叠加更多效果解决未接通的路由。

## 本机 `.fst` 的只读证据与格式缺口

2026-11-01，读取本机安装目录，未启动 FL：

| 文件 | 外层/私有 state | offset4 zlib 解压 | SHA256 |
|---|---|---|---|
| `C:/Program Files/Image-Line/FL Studio 2026/Data/Patches/Plugin presets/Generators/Sytrus/Default.fst` | FST format48；事件213=1146B；state前4字节`13000000` | 64854B，流完整，无unused/trailer | `b0f5320ac532620c79d6cf45af32818063bae1066d02b9743d44f04b1985aaab` |
| 同目录 `Default subtractive.fst` | FST format48；事件213=1032B；前4字节`03001700` | 64821B，流完整，无unused/trailer | `88ce835eef083b518df5f497239f331037b93886c9e2d21281e4d8bb05799ce4` |

这些观察只证明具体文件的容器/压缩结构，不证明前4字节代表某个固定版本，也不证明任意偏移可写。官方手册没有公开私有序列化规范。本次公开 GitHub 仓库检索没有找到可作为证据的 Sytrus state codec；`a1exwang/fm-synth` 是独立 Python 合成器，`juicyslew/Apricot` 是受 Sytrus 启发的独立合成器，不能充当 Sytrus 格式实现。

本轮已通过受控单变量配对完成 Default 家族的 FM/RM、ratio、SH、前32谐波与四点音量包络适配，见[真实接口与验证](../sytrus.md)。其他布局仍拒绝写入。进一步扩展要保存原生配对状态，先证明局部修改和未知区域保留，再证明 FL 重开和音频；不能仅按相邻字段猜测更多参数。

# 真实插件音色设计与编曲上下文适配

设计日期：2026-11-01。基于 CLI 1.0.3 源码、现有 `.lab/fullstack` 证据和本轮读取的插件官方手册。本文是实施与验收计划；未把计划中的命令或音色写成已经实现。现有 `AGENT-USAGE.md`、`docs/fullstack.md` 未提交修改保持原样。

## 要交付的能力

主代理能把一个明确音乐角色交给音色设计执行者。执行者读取真实编曲，使用真实插件，从 init 合成或改造指定 preset，提出多个实质不同的声音，在相同 MIDI 与上下文中导出、匹配试听响度、比较并修改，最后返回可重开、可应用、可撤回、可继续编辑的完整状态。

首批重点是 **Sytrus 深层设计**，以 **Surge XT** 验证不同插件机制和通用控制层。Sytrus 必须跨过现有主音量、音高等宿主旋钮，实际覆盖 FM/RM 矩阵、算子音高关系、波形/谐波、包络点及相关路由。3x Osc 可作为轻量探针，不替代 Sytrus 重点，也不计作本批完成的捷径。

最终最小验收集为低音、主奏/拨弦、铺底三种角色，每种至少三个实质不同候选，共九个。每种角色包含 Sytrus 与 Surge，至少一个 init 和一个 preset 改造；整套两个插件均覆盖 init 与 preset。完成第一垂直切片之后继续完成九候选、上下文修订和交接回滚，不将切片当最终交付。

## 当前可复用的事实与缺口

| 现有入口 | 当前源码/本地证据 | 本任务必须补齐的部分 |
| --- | --- | --- |
| `session start/save/stop` | `sessions.py` 创建独立 Desktop、进程创建时间与 controller 绑定；FL 实际保存后移除 ownership marker；新路径输出 | 把保存的完整 FLP 作为候选检查点，管理候选与应用前后状态；验证插件能实际保存后冷重开 |
| `live plugin-find/plugin-apply/plugin-job` | 名称/索引解析；每批 1–32 参数；读前状态、写后回读、可归因回滚；单 worker 同时只有一个参数事务 | 插件语义、真实单位、离散值、结构性编辑；跨多批的失败恢复不能只靠最后一批回滚 |
| `session verify-params` | 保存后另开 worker；对插件名、数量、参数索引/名称和数值做观察/断言 | 只覆盖显式列出的宿主参数；不能证明谐波、矩阵、调制连线、资源和整条声音状态完整 |
| `sytrus.py` | 已有宿主 initial controls；明确排除 FM/RM 矩阵、谐波编辑和包络点；`null` 表示值仍由 opaque preset 持有 | 独立 Sytrus 深层状态操作，不能将新增参数枚举包装成深层支持 |
| `plugin_state.py` / `plugin_profiles.py` | 少量已知原生布局及 raw overrides；未知字节保留 | 保存/移植完整插件状态及它依赖的 host overrides、通道声音设置和指定 FX |
| `set_channel(plugin_preset)` | 当前只替换 event 201/212/213，移除 sample 路径并清除旧插件宿主初值 | 不足以作为通用完整音色导入：须明确移植范围、重绑定宿主初值、保持主工程身份和自动化 |
| `notes` / `project edit` / Playlist | 文件级精确音符与编排；保存 IID 与当前 channel index 分离 | 从真实段落提取固定比较短句与角色上下文；不能用换 MIDI、换八度掩盖音色差异 |
| `render wav` / `audio inspect` | FL 原生 Song 导出；PCM、静音/截断检查；peak/RMS/crest 与每声道电平 | 固定导出窗口与尾音，solo/context 两类渲染，实际响度测量与匹配；当前没有 LUFS 或 true-peak |
| `project snapshot` / `diff` | 有界概览及省略标记；语义 diff 明确不解释未知私有插件状态 | 概览供代理理解上下文，完整 FLP/插件与 FX bytes 才是恢复源；不能以 snapshot 相等证明完整声音未变 |

可复用而不必重跑的历史证据：`.lab/fullstack/plugins-runtime/observations.json` 的双 Surge 实例隔离、20 参数、失败/取消恢复和重开；`.lab/fullstack/independent-20261028/review/completion-results.json` 的构建→修改→FL 保存→重开→WAV 路径。这些证明基础设施，不证明本次音色质量。

必须保留的反例：`discrete-results.json` 中 Surge Scene Mode 请求/宿主回显 `0.37123`，重开为 `0.335`，显示为 Key split。因此 `host_readback` 成功不等于离散语义或持久化成功。

## 第一条真实垂直切片

**先交付 Sytrus init 的两算子 FM 低音，再扩为同一低音角色的三个候选。** 所有步骤都在 CLI-owned private worker 中执行，不向用户 FL PID `129388` 发命令、窗口输入或结束请求。不要为了可见 UI 启动会向已有编辑器转发项目的 interactive 模式。

1. 从安装的 Sytrus Default 创建新工作副本，保存 init 的真实状态，明确输出 carrier、调制 operator、ratio/offset、FM/RM 开关和当前路由。先做一次实际保存、退出 owned worker、冷重开、固定音符导出，实测本机插件可恢复性；不根据名称或 edition 猜许可，也不执行购买或安装动作。
2. 明确设置一个 `OP2 -> OP1` FM 单元、OP1 到输出，设置两个算子的音高关系、独立音量包络。通过原生操作改变矩阵，而不以 OP2 volume 的间接改变冒充矩阵写入。比较关闭/开启这条调制的对照音频与实际保存状态。
3. 形成低音 A（圆润、有短促 FM 瞬态）、B（不同调制关系/波形或 RM 的中频粗粝音色），第三个为 Surge 的减法低音或实质改造 preset。每个候选从已记录的起点分支，禁止候选间意外继承上一个声音的内部状态。
4. 使用同一真实低音短句：音高范围、速度、velocity、gate、长短音和休止都固定；在含 kick、和声及节奏的相同编曲段落内导出。先得到 raw solo 和 raw context，再制作匹配电平的试听版本。
5. 听辨/测量后只为具体问题修改一次：例如 kick 重叠、短音不清楚、尾音越过休止、单声道低频变弱。保存修改前后，说明改变了什么、为什么，以及哪段声音证明效果。
6. 选一个候选定向应用到基线主工程的新副本；保存、冷重开、重渲染。撤回后恢复目标声音且其他通道不变，再次应用并继续改一个合成参数，确认交付不是只能播放的 WAV。
7. 在另一工作分支注入一次中途失败/取消，恢复到上一个完整检查点，重开出音。此时才完成最短闭环；随后按下文矩阵扩完三角色。

第一切片优先关闭“会改声音但不能交接完整状态”的缺口。不要先做预设评分、全部参数导出、插件百科或大量声学特征而迟迟没有 FL 保存重开后的声音。

## Sytrus 深层操作的最短可行路线

### 已核实的原始资料

本轮 HTTP 200 读取 [Sytrus 官方手册](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/Sytrus.htm)，直接用于正在验证的操作：

- `#Sytrus_modmatrix`：矩阵路由具有方向；调制 OP1 的 OP2 与直接输出 OP2 不是同一个信号。官方明确说矩阵 modulation knobs 不能自动化，operator volume 可控制调制幅度，但不能替代任意矩阵结构编辑。
- `#Sytrus_operator` / `#Sytrus_harmonics`：ratio 与 Hz offset 分开；内置 default ratio 的显示不能按通用合成器的“1 倍基频”假设。Harmonics Editor 支持导入单周期 WAV，把其分析为谐波设置，不是播放外部采样；也可导出单周期 WAV。
- `#Sytrus_envelopes`：原生包络支持点、曲线、sustain/loop/release 语义及 Open/Save state（`.fnv`）。只改 Main ADSR 缩放不等于编辑算子包络。
- 主模块区分 draft 与 rendering quality。固定两者及 oversampling 设置，解释实时预听与离线导出的差异。

本轮对本机 factory 文件只读观察：`Default.fst` 的 event213 长 1146 字节，前四字节之后可 zlib 解压为 64854 字节；`Default subtractive.fst` 解压为 64821 字节；插件 `Data/Default.dat` 解压为 48197 字节。**这只是容器线索，不是已知私有格式，更不是可直接写入的偏移表。** 保留前缀为不透明字节，不称其固定版本号；不能按固定总长度推定布局。

### 实施顺序

1. **已有 public host 参数优先。** runtime 查询安装插件真实参数，核对算子音量、filter、包络缩放等当前可见部分。精确名字不唯一时用已绑定索引；保存 normalized 与 raw 单位差异，不猜 Hz/ms 映射。
2. **缺失结构用原生 owned UI 完成第一份真实样本。** 用 `session windows/screenshot/input` 及其窗口 receipt 进入 Sytrus，修改一个 FM cell、一个 RM cell、一个 harmonic、一个包络点，分别保存成成对夹具。每一步新截图/回读，窗口几何变化后重新绑定；输入提交本身不算成功。当前输入工具只有有限按键、左键和拖拽；如果导入 WAV/FNV 确实需要右键或路径文本，只扩充这两个具体原语，并保留 owned-window 绑定，不造通用 GUI 宏系统。
3. **原生导入可减少画图。** 可由明确的 harmonic amplitude/phase 合成单周期 WAV，再通过官方 Harmonics 导入，随后检查 FL 实际谐波和音频。包络可使用 FL 自己保存的 `.fnv` 作为起点；非公开格式未验证前不能自行拼装 `.fnv`。单周期音频是插件输入材料，最终仍由真实 Sytrus 合成/渲染。
4. **只有出现实际重复成本才做局部状态 patch。** 解压比较“同一起点、只改一个控件”的原生保存对；每一类至少验证一个非默认值、回到原值和另一不同音色起点。稳定识别后，仅在该 Sytrus build/布局启用矩阵/谐波/包络局部编辑，保留未改 bytes、前缀和未知块；FL 重开并重新保存后的语义与音频为通过条件。两个控制器的联动变化不能冒充一个简单字段。
5. **不等待全格式逆向。** 原生 UI 能完成的深层候选继续做并保存完整状态；未稳定的结构能力保留 `owned_ui` 或明确 `unknown/unsupported_layout`。同样不能用预先调好的完整 preset 替代从 init 的实际结构操作。每个支持项标明 host、原生 UI、已验证 layout patch 哪条路径实际完成。

## 通用层与插件专用知识

通用层仅负责绑定目标、工作副本/事务、完整检查点、固定短句与编曲、渲染/测量、应用/撤回以及结构化回执。复用 `sessions.py`、`live.py`、`native.py`、`flp.py` 和已有 Result，不引入任务调度平台、数据库或第二种 RPC。

插件专用层负责：init 定义；可用机制；参数身份与真实单位；离散合法状态；操作顺序；声部/调制/包络语义；必要的原生 UI 操作；完整状态包含哪些宿主数据；可用资源及已测版本。

首批插件支持记录按操作保存：`discover`、`init`、`continuous`、`discrete`、`matrix`、`harmonics`、`envelope_points`、`capture`、`apply`、`reopen`。每项给出实际 backend、验证范围和待解决限制。不要把插件名、参数总数或一次音量变化映射为“全插件支持”。

Surge 的使用以[官方手册](https://surge-synthesizer.github.io/manual/)的 oscillator、filter block、FM configuration/depth、amp/filter envelope 与 Scene Mode 为依据。本轮已读取手册；具体参数索引和离散值仍来自本机 FL。先用内置波形和真实可写路由避免无关资源依赖；若使用 wavetable/调制矩阵，必须实际加载/连接并保存，不能仅给候选起一个“wavetable pad”名字。

## 可分派请求与最小命令面

建议新增 `sound-design` 命令组，以下为**拟实现**契约；使用直接 JSON 请求与现有 Result envelope。开始可由一个 `sound_design.py` 串联现有模块，Sytrus 专用知识留在独立模块/数据中。命令命名可随实际实现收敛，但职责必须保留。

| 命令 | 输入与产物 | 成功含义 |
| --- | --- | --- |
| `prepare` | 基线 FLP、显式 target、角色 brief、段落/音符、约束、工作目录 → task JSON 与不可变基线 | 源与目标、依赖、比较短句/上下文已解析；尚未宣称设计完成 |
| `candidate` | task、parent candidate 或 init/preset、明确 design changes → 新候选 FLP、变化记录 | 真实插件操作已执行并由 FL 保存；未渲染/重开时仅 `artifact_ready` |
| `audition` | 候选、固定窗口/尾音/导出设置 → raw 与匹配版 solo/context WAV、测量 | 指定项目被真实 FL 导出；测量范围明确 |
| `checkpoint` | 候选 → FL 原生保存、冷重开观察、状态与音频比较 | 完整检查点的恢复范围被验证，不只是参数回显 |
| `apply` | 候选、目标主工程、显式声音范围 → 新工程、应用回执与 before checkpoint | 完整声音定向应用，其他工程内容保留 |
| `restore` | 应用回执或已保存 checkpoint、当前目标 → 撤回新副本 | 只在仍可归因的范围恢复；冲突不覆盖主代理后续修改 |

`prepare` 的最少信息：

```json
{
  "source_project": "ABSOLUTE_BASELINE.flp",
  "target": {"channel_index": 2, "expected_plugin": "Sytrus"},
  "role": "bass",
  "brief": "与 kick 留出瞬态空间，短音清楚，低频居中；给出圆润与粗粝的可比较方向",
  "section": {"arrangement": 0, "start_tick": 0, "length_tick": 3072, "tail_seconds": 3},
  "notes": {"source": "existing_target_score", "allow_changes": false},
  "constraints": {"preserve_tempo": true, "preserve_other_channels": true},
  "work_dir": "ABSOLUTE_NEW_DIRECTORY"
}
```

解析后记录 source SHA256、saved IID、当前 global index、插件身份/版本或可核实 module/class-ID、PPQ/tempo/meter、段落与实际 note 内容。role 的 octave、velocity、密度和 gate 从原工程读取；source score 为空时由 brief 明确生成测试句并保存，不能暗中采用预设示例 MIDI。

每个候选必须记录 `origin`（init/preset/parent）、设计假设、结构/参数改变、实际 observed 值、监听证据、限制、下一步建议。preset 改造必须在振荡器/调制/包络/滤波等合成结构上有实质变化，只有 master gain、混响大小或 preset 名称变化不合格。

## 状态、应用与撤回

完整候选交付以 FL 原生保存的 FLP 为权威恢复源，并包含设计所用的插件/Wrapper bytes、通道声音设置、host current/initial controls、指定 FX 链与其状态/干湿/旁路、相关自动化和资源依赖。摘要 JSON 是索引与解释，不是重建私有状态的唯一来源。`.fst` 可作为经过原生导入复验后的便携附加物，不代替 FLP 检查点。

定向应用要区分 **声音范围** 与 **工程身份**：保持目标 channel IID、已有 notes、Playlist、其他 channel、路由和未授权的 mixer/send；仅覆盖请求明确列出的声音字段和指定 FX。候选依赖某条 route、send、包络或自动化时必须纳入范围并在回执列出。不能把整份旧工程覆盖新工程来宣称“应用音色”。

现有 `plugin_preset` 分支清除旧 host 初值，新的完整状态迁移必须同时重绑定候选的相关初值和运行当前值。一个声音可能被宿主自动化重新写回旧值，因此有相关 links/events 时必须显式保存、复用/重绑定或拒绝不兼容替换，不静默抹掉曲线。复制插件状态不能将保存的 IID 当当前 global index。

应用前写不可变 before checkpoint；应用回执包含精确目标、受影响字段/状态哈希与新 FLP。主代理后来改了 unrelated 通道时，撤回应保留该修改；若同一声音范围已经继续编辑，拒绝盲撤回，允许选择新分支从 checkpoint 继续。复用完整状态局部复制和已有 diff；不要求建立通用三方插件合并器。

资源只收集实际用到的样本/波表/IR/FNV 等及校验值和来源路径，不能复制整个插件库。已嵌入 Sytrus 谐波的单周期输入应记录出处，但是否仍需运行时依赖由重新打开证据决定。缺依赖、插件缺失、trial 恢复失败必须给出真实结果，不以占位音源替代。

3x Osc 的[官方手册](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/3x%20Osc.htm)明确提示 plugin preset 通常不足，须完整 Channel preset 保存集成 Sampler 设置。这是通用完整状态边界的重要反例，未来扩展时必须包含实际使用的 host envelope/filter/polyphony 等。

## 试听、上下文与响度

所有同角色候选固定同一段 MIDI、velocity、gate、tempo、sample rate、render quality、有效比较窗口和尾音；记录实际 FL 导出设置。solo 保留该声音自身所需 FX；context 保留同一编曲、路由、侧链和 master chain。不要通过 solo/mute 不经意断开 sidechain 输入。若公共 bus 非线性处理使 solo 与 context 不可直接相减，就分别解释，不伪造“完全隔离的 stem”。

原始导出永久保留；仅比较副本作线性增益。新增响度测量可复用安装的 FFmpeg `ebur128`/其他已验证 BS.1770 实现，并记录工具版本、窗口、gating；现有 `audio inspect` 仍仅报告 PCM peak/RMS，不能把 RMS 改名 LUFS。

- 对足够长的有效音乐窗口，以相同 LUFS 目标匹配，匹配后复测偏差不超过 0.5 LU；目标由可实现 headroom 决定，初始可用 -23 LUFS。若任一候选提升后超过约定 true-peak 上限，整体降低共同目标，不以 limiter 改变音色后假装只匹配响度。
- 极短/稀疏信号导致 integrated loudness 不稳定时，延长同一短句，或明确使用固定活动窗口的 RMS/短时响度匹配并标注方法。不得删除候选不同的 attack/release 后再比较。
- solo 比较用相同试听响度；context 比较先固定伴奏和目标乐器的校准增益，再真实重渲染。不要对每个完整 mix 单独归一化而悄悄改变伴奏基准。可另附整段 mix 匹配副本，但必须与固定伴奏版本区分。
- 三角色分别报告 transient/尾音、频段分布、立体声/单声道表现和 clipping 等必要指标。频谱差异只证明信号不同；“适合低音/听得清/有层次”的结论要指向实际段落的听辨记录，不由几个阈值自动判定。

冷重开重渲染的再现判定不能要求所有 WAV SHA256 一致：自由振荡器、unison 和随机调制可以合法改变样点。先在同状态重复导出建立本机变动范围；确定性测试可比较对齐波形，随机音色比较同窗口响度/包络/频谱及听感。建议初始检查 loudness 差不超过 0.5 LU、时长/关键 onset 一致，再以重复导出范围解释合法随机差异；异常则回查状态，不能放宽到任何声音都过。

## 最小音乐候选矩阵

以下是要实际试验的方向，不是未经试听就宣布成立的成品描述。若某个方向不成立，应换实质不同方案并保存淘汰原因。

| 角色 | 候选 A | 候选 B | 候选 C | 上下文要解决的问题 |
| --- | --- | --- | --- | --- |
| 低音 | Sytrus init：两算子 FM，短调制瞬态、稳定基音 | Sytrus init：不同 ratio/波形与 RM 或不同 FM 拓扑，中频更突出 | Surge preset 改造：振荡器/滤波/amp envelope 改为紧致减法低音 | kick 让位、低频单声道、短音清晰、句间余量 |
| 主奏/拨弦 | Sytrus init：FM bell/pluck，独立 carrier/modulator 多点包络 | Sytrus preset 改造：改变 harmonic 内容与调制路由/包络，形成另一攻击和衰减 | Surge init：pulse/saw 减法主奏，filter envelope 与 velocity 配合 | 主旋律辨识、与和声中频冲突、长短音、velocity 响应 |
| 铺底 | Sytrus init：明确的 additive/harmonic 设计、慢多点包络与 filter path | Sytrus preset 改造：重设 FM/RM 关系与包络演变，形成另一频谱/动态方向 | Surge init：失谐多振荡器减法 pad 与慢 filter/amp envelope | 和声厚度、lead 留位、尾音跨和弦、stereo/mono |

九个候选中至少六个以 Sytrus 为核心；必须确实使用 FM、RM、自定义 harmonic 和多点包络这些重点能力。两个插件在整套中均有 init 与 preset 起点。必要时调整具体候选分配以满足这一覆盖，但不要做无用的插件×角色×预设笛卡尔积。

“实质不同”至少同时满足：结构/源波形/调制/包络等存在可说明的差别，响度匹配后音频差异仍成立，同一短句/上下文可以解释其用途差异。单纯音量、pan、名称、随机种子或微小参数抖动不算新候选。

每个角色至少对一个候选根据 context 问题进行一次修订，留下前后 raw/matched 音频与状态。角色最终选择允许与 solo 最悦耳的候选不同，选择理由必须对应编曲。

## 可分派工作包及顺序

| 顺序 | 工作包 | 具体产物与完成条件 |
| --- | --- | --- |
| 1 | Sytrus 真实深层路径 | init→FM/RM/harmonic/envelope 的原生保存样本，先完成最小 FM 低音；读取本机身份/保存重开，不猜格式 |
| 2 | 状态交接 | 完整候选 checkpoint、定向 apply/restore、host overrides 与关联自动化处理；应用、撤回、再修改真实出音 |
| 3 | 音频比较 | 固定短句/段落与 tail、solo/context 原生渲染、响度测量及匹配；先完成低音三个候选 |
| 4 | 三角色设计与修订 | 九候选及三次 context 修订，Sytrus 重点、Surge 对照；失败候选有原因和替代方案 |
| 5 | 主代理交接验收 | 主代理只凭请求/回执重开、比较、应用/撤回并继续改；失败恢复检查；同步真实 capability/help/使用文档 |

任务可以按这些工作包分派，但同一 owned worker 只允许一个写入执行者。独立文件比较/声学分析可并行，候选操作有顺序依赖时不并行控制同一插件。工作包之间传完整路径、目标绑定、结果状态和下一检查点，不依赖子代理记忆。

## 验收矩阵

| 编号 | 必须实际执行 | 通过证据 | 不足以通过的替代物 |
| --- | --- | --- | --- |
| SD01 | 新建 owned FL26 worker，基线/用户编辑器保持独立 | FL build、PID/创建时间、controller 绑定，源文件未改；用户 PID129388 未被操作 | mock host、只验证 FL.exe 文件存在 |
| SD02 | Sytrus init 保存、关闭、冷重开、演奏/渲染 | 原生 FLP、重开状态与非静音 WAV；实际许可/恢复结果 | 插件已安装、可在 UI 打开 |
| SD03 | Sytrus FM/RM 方向与真实 matrix edit | 一条明确连线的前后原生状态、重开观察、对照音频 | 仅改 operator volume 或 master gain |
| SD04 | Sytrus 自定义 waveform/harmonic 与多点 envelope | 实际谐波/点/loop-release 改变、完整保存重开、相应频谱/时域变化 | Main ADSR 缩放、加载现成复杂 preset 后不改 |
| SD05 | Surge 的另一合成/控制机制 | runtime 参数身份、实际结构变化、原生保存重开、声音 | 4240 参数枚举或一次 volume setter |
| SD06 | 离散参数有效值 | 请求、settled observation、语义/显示、冷重开归一后的值；不一致明确失败或记录实际合法值 | host numeric echo 相等 |
| SD07 | 三角色各至少三实质候选 | 九套 origin/设计变化/完整状态，同 MIDI 的 raw 与匹配 solo/context | 九个名称、换 MIDI、只换 preset、纯增益变体 |
| SD08 | 响度公平比较 | 测量算法/版本/窗口、前后 loudness、增益、peak/headroom、固定伴奏说明 | peak normalize、把 RMS 叫 LUFS |
| SD09 | 每角色至少一次 context 修订 | 具体冲突、改动、前后音频及选择理由 | solo 指标排序或未经听辨的美学结论 |
| SD10 | 所有交付候选完整状态冷重开 | 全部 FLP/依赖、关键深层状态读回/观察、solo/context 重渲染在实际变动范围内 | 只检查已暴露参数、不打开 FL 的 bytes roundtrip |
| SD11 | 主代理 apply→reopen→restore→reapply→continue | 主工程新副本、目标状态恢复、其他通道/notes/Playlist/FX 不变的读回；继续修改又保存出音 | 用 WAV 替代可编辑插件，整工程覆盖“应用” |
| SD12 | 取消/失败后恢复 | 中途失败仅影响 owned 分支，从 before checkpoint 冷重开出音；部分执行状态如实记录 | 只捕获异常、参数失败却将候选标 ready |
| SD13 | 目标/依赖真实失配 | 插件/目标改变或缺实际依赖时明确拒绝/unknown，保留完整 checkpoint | 静默换插件、零值兜底、覆盖后续编辑 |
| SD14 | 可分派、可复用 | 主代理不靠执行者隐含记忆完成一次新 brief 的 prepare→候选→试听→应用 | 只有 `.lab` 一次性脚本或孤立 demo |

测试只围绕新增行为：目标绑定、局部状态复制保留无关 bytes、离散值归一、应用冲突/恢复和音频匹配计算。每个独立风险用一个最小夹具加对应真实 FL 流程；不把增加测试数当设计能力或音质证据。已有通过的基础设施检查可复用，代码变化触及其行为时才回归。

## 失败恢复与交付状态

每批参数写完先等真实 job 终态，再进行保存或下一步。跨多个 32 参数批次、GUI 结构改动、加载 preset 的恢复边界都是上一个完整 FLP checkpoint；不得将某一批 `restored` 夸大为整个候选撤回。worker 崩溃、modal 阻塞或保存超时后只检查/关闭自己创建且身份匹配的进程，保留已保存产物和错误，重新开新的 owned 分支恢复。

结果使用现有 `planned/artifact_ready/verified/partial/unknown/rejected/failed`，配明确 scopes：例如 `host_readback`、`native_saved_state`、`cold_reopen`、`solo_render`、`context_render`、`loudness_match`、`scoped_apply`、`restore`。监听尚未完成时不说“音色优秀”；完整恢复未过时不说“交付完成”。

交付目录只需一份 task/候选索引、真实 FLP 检查点、必要资源、raw/matched WAV、实际观测/比较结果与简短选择说明。首批不需要独立 Web UI、向量检索、预设推荐模型、全插件 schema、通用私有格式解码器或外部服务。公开文档按已经验收的操作声明能力，保留真实限制和失败案例。

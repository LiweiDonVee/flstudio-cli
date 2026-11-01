# Sytrus：从本机 Default 设计可实际加载的音色

1.2 已补充 OP→滤波器、OP/filter→FX/OUT、PAN 与四点 CUT 包络；具体请求见
[已实测 Producer 能力](../producer-1.2.md) 和 Skill 的
[Sytrus 配方](../../skills/flstudio-sound-design/references/sytrus.md)。
下文保留1.1初始算子校准记录；滤波/FX路由不再是未实现项。

`flstudio_cli.sytrus_design` 补充宿主参数目录之外的受控能力：FM/RM 算子矩阵、直接输出、六算子 ratio、SH 波形变形、前32个谐波的线性系数、启用并编辑四点音量包络。它修改工程副本中的真实 Sytrus state；不是宿主 initial-control 覆盖或屏幕旋钮模拟。

本机基准是 FL Studio Producer 26.1.6.5639，2026-11-01。原生界面配对、独立进程重开和 WAV 测量证据保存在不入包的 `.lab/sound-design/sytrus-adapter/`。接口使用标准库 `zlib`、`struct`，不增加运行时依赖。

## 请求

在 sound-design candidate 中使用 `sytrus_design`：

```json
{
  "init": true,
  "matrix": [
    {"mode": "fm", "source": 2, "target": 1, "value_raw": 80},
    {"mode": "rm", "source": 3, "target": 1, "value_raw": 0},
    {"source": 1, "target": "out", "value_raw": 256}
  ],
  "operators": [
    {
      "operator": 1,
      "ratio": 2.0,
      "shape_raw": 0,
      "volume_envelope": {
        "enabled": true,
        "attack_time_raw": 0.02,
        "decay_time_raw": 0.8,
        "sustain": 0.4,
        "release_time_raw": 0.3
      }
    },
    {
      "operator": 2,
      "ratio": 3.0,
      "shape_raw": 0,
      "harmonics": [{"harmonic": 2, "coefficient_raw": 0.25}],
      "volume_envelope": {
        "attack_time_raw": 0.01,
        "decay_time_raw": 0.4,
        "sustain": 0.1,
        "release_time_raw": 0.1
      }
    }
  ]
}
```

`init:true` 从本机安装的 `Data/Patches/Plugin presets/Generators/Sytrus/Default.fst` 载入合法工厂起点，并清掉目标通道旧插件的宿主参数覆盖。`preset` 可显式指定同一受支持布局的本地文件，必须与 `init:true` 一起使用；没有嵌入或分发 Image-Line 预设内容。未指定的设置沿用该起点，所以应显式写入所需 ratio、路由和包络，不把“工厂 Default”自动当成某种音乐设计。

`init:false` 或省略 `init` 会保留现有 state，要求它匹配下面的已定标布局。普通宿主控制继续通过 `sytrus`/`sytrus edit` 设置；若同一 candidate 同时使用两种请求，应先执行 `sytrus_design`，再设置宿主覆盖。

## 矩阵方向和单位

算子左上区域是**列为源、行为被调制目标**。`source:2,target:1` 等同 `row:1,column:2`。对角线是自反馈。每项可选择 `mode:"fm"` 或 `mode:"rm"`，默认 FM；两种状态同时保存，切换界面标签不会清除另一种调制。

`value_raw` 为整数 -256..256，256 是实际界面上限。负值保留原生极性；不要把符号解释为亮度评分。`source:1,target:"out"` 或 `row:1,column:"out"` 控制 OP1 直接输出，统一写 FM 表。RM 的 OUT 不作为另一条独立输出开放。

已实测方向：仅 OP1→OUT、OP2 ratio=3 时，FM 行1列2产生新的边带；行2列1保持 OP1 纯音。RM 同样对照确认。`matrix`保留6×6算子区域及直接OUT；1.2的`routes`另行覆盖OP→F1–F3与OP/filter→FX/OUT，`pan`覆盖算子/滤波器PAN。串行滤波Send to Next不作为任意矩阵边写入。

## 算子和包络

| 字段 | 合约 | 本机证据和边界 |
|---|---|---|
| `operator` | 1..6 | 每个算子可在一个请求中出现一次 |
| `ratio` | 0..64，最多4位小数 | 实际界面2.0000→64.0000配对，整数存储为 ratio×10000；另有1.5/2.25/3.25冷重开证据 |
| `shape_raw` | SH整数0..512 | 实际界面0→512改变波形；128/256冷重开保存通过。它是SH modifier，不能在任意原始波形上直接称为“方波/锯齿” |
| `harmonics` | harmonic 1..32；`coefficient_raw` 0..1 | 线性浮点系数，未列出的谐波保留。UI柱高是对数显示，不能把UI50%当成0.5系数 |
| `volume_envelope.enabled` | 布尔值 | 传入非空包络时默认 true；显式 false 可关闭。factory Default 的个体 VOL ENV 原本关闭 |
| `attack_time_raw` / `decay_time_raw` / `release_time_raw` | 原生分段时间，0..10000 | 保持 raw 名称；不是已认证的秒、毫秒或跨 tempo 的统一换算 |
| `attack_level` / `sustain` / `end_level` | 0..1 | 对应第2、3、4点的电平；未指定保持原值 |

包络保持四点、既有 sustain/loop 标记和 curve tension；不新增点，不修改曲线类型、随机映射或 tempo 模式。提供包络时会明确启用它，避免“曲线改了但对音频没有作用”。调制源 OP2 的 VOL ENV 可改变 FM 强度随时间的变化；OP1 的 VOL ENV 主要塑造输出幅度，两者应按目标分别设计。

音高要按实际 `Note.key` 与导出测频核验。本次 `Note.key=36`、master pitch=0、offset=0、同一安装上：

| OP1 ratio | 实际纯音主峰 |
|---|---:|
| 1.0000 | 65.441 Hz |
| 2.0000 | 130.882 Hz |

这证明 ratio×2 提高一倍频率，也表明不能把“ratio=1”与某个 MIDI/FL/Codex 音名转换混为一条未经验证的固定 Hz 结论。

## Python API

```python
from flstudio_cli.flp import Project
from flstudio_cli.sytrus_design import initialize, inspect_design, apply_design

project = Project.read("source.flp")
receipt = apply_design(project, 0, request)
project.save("candidate.flp")
observation = inspect_design(Project.read("candidate.flp"), 0)
```

`initialize(project, channel, preset=None)` 仅载入本地起点。`apply_design` 在独立内存副本完成全部校验后再替换目标工程事件，错误不会遗留半个矩阵或半次 init。它不自动操作已打开的编辑器，不自动写文件，也不声称已经播放。返回的 `live_applied` 为 false，`readback_scope` 为 `saved_private_state`。

`inspect_design` 返回矩阵有向边、直接输出、ratio、SH、非零谐波、音量包络 enabled/ADSR 及诊断性的原始点记录。它与别名 `inspect`、`apply` 一并可导入。

## 支持布局和证据

| 布局 | 不透明前缀 | 解压长度 | 定位与校验 |
|---|---|---:|---|
| 本机 factory Default | `13000000` | 64854 | 算子起点1443，跨度6976；六算子内重复包络、wave modifier相邻结构锚点 |
| FL26原生保存的同一起点 | `03001900` | 64871 | 算子起点1210，跨度7000；同样逐算子验证锚点 |

前4字节只做精确 profile 匹配，不被解释为统一版本号。除长度、前缀外，还核验全部六算子内的重复结构、字段范围和四点包络。真实 `Default subtractive.fst` 被明确拒绝；不能仅因插件名称或解压成功就应用偏移。

factory→native 时，FL 会升级包络内部序列化，并把全部18个非首点的 `flags_raw` 从0规范化为 `0x01000000`；部分坐标经 float32 精度收敛。这是已观察到的转换，不能要求首次原生保存的完整压缩 blob 与旧 factory 完全相等。首次比较公开语义值（浮点容差1e-6）；原生保存→独立冷重开则另行检查稳定性。未知 flags/curve tension 保留，不把该观察推广为任意历史曲线的解释。

2026-11-01 的 `.lab/sound-design/sytrus-adapter/acceptance-131338/report.json` 包含 **24/24** 检查、4份独立 private worker 冷重开/原生保存/WAV。compound 案例涵盖 FM80、RM-96、OUT192、ratio1.5/2.25/3.25、SH128/256、谐波和已启用包络。系数2/3/7/16/32分别设为 .5/.25/.15/.12/.1 后，实际频谱相对振幅为 .500366/.250158/.150122/.119968/.100088。快、慢包络在20–80ms窗的RMS为 .081824/.039047；1.0–1.1s尾音窗为0/.005461，证明包络确实影响原生音频。

所有实验由 `sessions.start(..., desktop_mode="private")` 建立独立受管进程，使用随机RPC前缀、进程创建时间和所有权标记校验；没有操作用户已打开的FL进程。界面定标只在私有桌面线程执行，不调用 `SwitchDesktop`。产品适配器本身无需GUI输入。

官方机制参考：[Sytrus manual](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/Sytrus.htm)。音乐设计流程与完整机制范围见 [Sytrus知识页](knowledge/sytrus.md)；旧宿主参数接口见 [Sytrus与混音](../sytrus-mixing.md)。

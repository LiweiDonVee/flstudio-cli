# Sytrus 与混音工作流（0.5）

保存工程 → CLI 写新副本 → FL 原生导出 WAV。文件操作不修改当前编辑器内存。
以下功能已在 FL Producer 26.1.6.5639 实际出音验证；索引从 0 开始。

## 找音色、改 Sytrus

```powershell
flstudio plugin presets --plugin Sytrus --search bass --limit 10
flstudio sytrus params --project song.flp --channel 0 --search master
flstudio sytrus edit --project song.flp --channel 0 --request synth.json --output pitched.flp
```

`synth.json` 是数组，使用整数宿主单位：

```json
[{"param":"master_pitch","value_raw":12},{"param":"master_level","value_raw":80}]
```

`master_pitch` 的单位是半音。参数目录还包括主包络、unison、Mod X/Y、六个 operator 的
相位/音量/音量包络、滤波器、chorus/delay 和 EQ；范围由 `sytrus params` 返回。
保存参数沿用宿主 initial controls，Sytrus 的压缩音色状态保持原样；由本机 FL 加载原音色。
已实测主音高 +12 约升八度、主音量 0 静音，并验证保存 IID 不等于数组序号时不会串通道。
其余参数采用对应宿主整数 ID，不把每个旋钮都标成单独做过音频认证。

返回 `value_raw:null` 表示值仍在未解析的音色中，不能当成 0 或默认值。
FM/RM 矩阵、自定义谐波、包络曲线点仍通过完整 `.fst` 音色或 GUI 处理。

## 一份请求完成混音

build 和 edit 都可包含 `mixer`、`fx_chains`、`sytrus`、`plugin_params`。
完整可运行的新曲请求见 [sytrus-mix.json](../examples/sytrus-mix.json)。

```json
{
  "channels":[{"index":0,"mixer_track":1}],
  "mixer":[
    {"track":1,"name":"SYNTH","routes":[6],"sends":[{"to":6,"level":0.75}]},
    {"track":6,"name":"SYNTH BUS","routes":[0],"volume_raw":12000}
  ],
  "fx_chains":[{"track":6,"slots":[
    {"slot":0,"preset":"C:/Program Files/Image-Line/FL Studio 2026/Data/Patches/Plugin presets/Effects/Fruity Parametric EQ 2/Default.fst"},
    {"slot":1,"preset":"C:/Program Files/Image-Line/FL Studio 2026/Data/Patches/Plugin presets/Effects/Fruity Soft Clipper/Default.fst"},
    {"slot":2,"preset":"C:/Program Files/Image-Line/FL Studio 2026/Data/Patches/Plugin presets/Effects/Fruity Reeverb 2/Default.fst","wet":0.25}
  ]}],
  "plugin_params":[
    {"channel":0,"param":"master_pitch","value_raw":12},
    {"track":6,"slot":0,"param":"main_level","value_raw":-300},
    {"track":6,"slot":2,"param":"decay","value_raw":20}
  ]
}
```

执行：

```powershell
flstudio project edit --input song.flp --request mix.json --output mixed.flp
flstudio project inspect --input mixed.flp --summary
flstudio render wav --project mixed.flp --output mixed.wav
```

`routes` 是完整目的地列表；`sends` 更新指定连线的旋钮位置，省略的连线保留。
二者同时给出时，send 目的地必须在 routes 中。`level` 范围 0..1，1=unity；它是 FL 的
非线性发送旋钮单位，不是线性振幅。0 是保留连线但不发送音频，可作 sidechain-only 连接；
压缩器的侧链选择/模式还须由对应音色或实时宿主参数设置。断线应从 routes 移除目的地。
重复指定已有路由会保留发送电平。

Mixer 推子 `volume_raw` 为 0..16000，12800 是 unity；声像 `pan_raw` 为 -6400..6400。
`muted:true` 静音轨道；`effects_enabled:false` 旁路该轨整条 FX 链。

## 复制、移动、重排、移除效果

`fx_chains[].slots` 定义该轨**完整的新链**，省略的槽会清空；`slots:[]` 清空该轨效果。
每个占用槽恰选 `preset` 或 `copy_from`，可另设 `enabled`（旁路开关）和 `wet`（0..1）。
只改一个槽的开关/干湿时，也须列出其余要保留的槽，使用各自的 `copy_from`。

```json
{"fx_chains":[
  {"track":1,"slots":[]},
  {"track":6,"slots":[
    {"slot":0,"copy_from":{"track":6,"slot":1}},
    {"slot":1,"copy_from":{"track":6,"slot":0},"enabled":false,"wet":0.5},
    {"slot":2,"copy_from":{"track":1,"slot":0}}
  ]}
]}
```

所有 `copy_from` 从本次链修改前的快照解析，因此跨轨移动、交换不会先删除来源。
复制/移动保留完整受支持插件状态、宿主参数覆盖、旁路和干湿，并重绑 wrapper 的轨道/槽号。
换新预设会清理旧插件的宿主覆盖，避免参数串到新效果器。`copy_from` 移动效果器时，
自动化链接的来源、目标和 Pattern 控制事件跟随原效果器身份迁移，当前值与播放起始值分别保留。
原位置仍保留该身份时，链接留在原处；删除被链接效果或复制到多个新位置且无唯一去向时，
请求会在修改前拒绝。与本次效果链无关的自动化不阻止编辑；原文件不会改变。

## 效果器参数

```powershell
flstudio plugin presets --kind effect --plugin 'Fruity Reeverb 2' --search default
flstudio plugin params --project mixed.flp --track 6 --slot 2
```

`plugin_params` 支持的保存状态 profile：

| 效果器 | 参数 |
|---|---|
| Fruity Parametric EQ 2 v8/354 bytes | 7 段 gain/frequency/width、main_level；gain/main_level 为 centidB，-600=-6dB |
| Fruity Reeverb 2 / 53 bytes | high_cut、low_cut、predelay、room_size、diffusion、decay、high_damping、bass、crossover、stereo、dry、early_reflections、wet |
| Fruity Soft Clipper / 8 bytes | threshold、post_gain |
| Fruity Limiter v5/161 bytes | gain、ceiling |
| Emphasizer v2 | 既有 Emphasis 归一化 `value`，以及 `plugin verify` 的受控音频验证 |

新 profile 使用明确的整数 `value_raw`；除上面标注的 centidB/半音，不猜测 Hz、秒或 dB 曲线。
其他已加载效果器仍可通过实时接口读取/设置 FL 暴露的参数，或加载其完整 `.fst`。
`plugin verify` 的专用受控输入目前仍针对 Emphasizer；其他保存参数用实际工程的前后 WAV 验收。

## 实时音源参数

```powershell
flstudio bridge install-controller-extension
# FL 中重载一次 MIDI 脚本，随后无需重启工程
flstudio live query --command cli_capabilities
flstudio live plugin-params --channel 0 --search 'Master'
flstudio live set-plugin-param --channel 0 --param 'Main - Master pitch' --value 0.5
```

`--channel` 使用全局 Channel Rack 索引，控制器通过 `useGlobalIndex=True` 定位，
不依赖当前 Channel Group。已安装但未加载扩展时会报未知命令，不退回可能串通道的旧寻址。
效果器仍用 `--track T --slot S`。实时参数的 `--value` 是 0..1 归一化单位，
与文件 `value_raw` 分开；名称必须精确且唯一，写入需独立回读。`--dry-run` 不连接桥。

CLI 桥同时识别 TX 及 RX 回路里的协议响应，兼容 FL 自动将 RX 重新分配为输出的情况；
请求回声不会被当成响应或重复执行。无需反复手动调整端口。

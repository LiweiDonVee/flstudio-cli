# FL CLI 0.2：实际创作路径

运行项目内 `.venv\Scripts\flstudio.exe`。所有业务结果为 JSON，计数区分输入、保存文件和 FL 渲染。
命令修改新工程副本，绝不依赖当前卷帘或旧 MCP 的选中项。输入文件不会覆盖。

## 创建编曲

`project build --request song.json --output song.flp`，请求如下。时间是工程 PPQ 的整数 ticks；
默认本机 Basic 模板的 PPQ=96、4/4 每小节384ticks。

```json
{
  "tempo_bpm": 130,
  "channels": [
    {"name":"Kick","sample_path":"C:\\Audio\\kick.wav","mixer_track":1},
    {"name":"Bass","plugin_preset":"C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\Patches\\Plugin presets\\Generators\\3x Osc\\Default.fst","mixer_track":2}
  ],
  "patterns": [{"number":1,"name":"Beat","scores":[
    {"channel_index":0,"notes":[{"key":60,"start_tick":0,"length_tick":24,"velocity":100}]},
    {"channel_index":1,"notes":[{"key":36,"start_tick":1152,"length_tick":96,"velocity":85}]}
  ]}],
  "playlist":[{"pattern_number":1,"track":1,"start_tick":0,"length_tick":1536}]
}
```

可有多个 Pattern 和 Playlist clips。要重复段落，显式添加多个 clip；拖长一个 clip 不会凭空
创建更多音符。源 Pattern 未填满四小节时，FL 的导出末尾也可能按实际 Pattern 长度截短。
`sample_path` 和 `plugin_preset` 每通道二选一。`.fst` 必须来自本机已安装的插件。

加 `--dry-run` 只在内存中构造并验证结构，不创建 FLP、音频、脚本或状态文件。
成功构建返回 `artifact_ready`，表示保存的工程副本已回读，不表示打开的 GUI 已改变。

## 编辑已有副本

```powershell
flstudio project inspect --input song.flp --summary
flstudio notes list --project song.flp --pattern-number 1 --channel-index 0
flstudio notes replace --project song.flp --pattern-number 1 --channel-index 0 --notes kick.json --output revision.flp
flstudio project edit --input song.flp --request changes.json --output mixed.flp
```

`kick.json` 是音符数组。`changes.json` 可组合 tempo、channels、scores、patterns、playlist、mixer、effects：

```json
{
  "tempo_bpm": 128,
  "channels":[{"index":0,"volume_raw":9000,"pan_raw":-1000,"mixer_track":1}],
  "scores":[{"pattern_number":1,"channel_index":0,"mode":"replace","notes":[{"key":60,"start_tick":0,"length_tick":24,"velocity":90}]}],
  "patterns":[{"number":1,"name":"Verse"}],
  "mixer":[{"track":1,"volume_raw":11000,"pan_raw":0}],
  "effects":[{"track":0,"slot":0,"preset":"C:\\Program Files\\Image-Line\\FL Studio 2026\\Data\\Patches\\Plugin presets\\Effects\\Fruity Reeverb 2\\Default.fst"}]
}
```

`scores.mode` 为 replace 或 append。未指定的通道音符和未知工程事件原样保留。
通道音量原始量纲0..12800，混音推子0..16000，pan -6400..6400；不猜测各插件的 dB 曲线。
CLI 的 `pan_raw` 对通道和 Mixer 都以0居中；通道文件内部以6400居中，由 CLI 在读写时转换。
`channels` 也可修改 name、sample_path，或加载 plugin_preset。`playlist` 若提供则替换完整排列。

## FL 真正打开并渲染

```powershell
flstudio render wav --project mixed.flp --output mix.wav
flstudio audio inspect --input mix.wav
```

调用已安装的 FL64.exe，在独立 Windows 桌面运行官方批渲染；当前用户编辑器可以保持打开。
输出必须是新文件。渲染使用同目录的临时Song模式副本，结束即删除，原工程保存的模式/选择不变。
进程超时只终止该命令自己创建的worker，不动用户FL。成功还核对新WAV的格式、帧数、峰值/RMS、
预期编排时长和源hash；非空曲目输出全零或截短会失败。需要有意导出静音时显式加`--allow-silence`。
各声部与请求是否吻合由工作流或独立盲测另外检查。

## 可执行文件计划

`plan build --request request.json --plan-out plan.json`；request 使用 notes.replace 原来的模型，
额外写 `"output":"C:\\Audio\\revision.flp"`。计划绑定源 SHA 和目标通道 IID。
`plan apply --file plan.json` 校验源没有变化后写新副本。加 `--dry-run` 不写文件。

尚不提供内存工程附着、任意自绘插件控件、任意 Automation Clip 曲线编辑或已编辑变长 Playlist
记录的通用重写。遇到这些操作会明确缺失，不能把旧项目的 API 列表当成本 CLI 已支持。

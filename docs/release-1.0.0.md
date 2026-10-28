# flstudio-cli 1.0.0

`flstudio-cli` 1.0.0 是 Windows x64 / Python 3.12+ 的稳定版。它把 FL Studio 工程工作拆成三个可组合后端：保存的 FLP 文件、CLI 自己拥有的 FL worker，以及 FL 原生 WAV 导出。源工程永远只读，写操作产生新文件，结果在交付前回读。

## 这版交付的能力

- FLP 容器和语义读取：通道、Pattern/音符、Playlist、Mixer、Automation、Arrangement、Controller、Sampler 与常用通道字段。
- 保存工程编辑：音符变换、Pattern/频道克隆、Playlist pattern/audio/automation clip、变长记录尾部保留、Automation 点、Mixer 路由/发送/电平、Sytrus 宿主参数、常用原生效果器 profile、插件 Wrapper 设置和 Notebook 文本。
- 组合制作：一次 `project build` / `project edit` 完成音源、编曲、路由和效果链，改动只写到新的 FLP。
- 三方插件：实时参数按名称/索引寻址，写前快照、写后回读、失败恢复；独立 worker 保存并重新打开后可做持久化核验。
- FL 原生工作：私有 worker 的窗口观察、截图和 PostMessage 键盘/画布输入；Piano Roll 读写、真实 Pattern 录制、Mixer 插入轨扩展、Playlist 音频淡化均有专用 job 流程。
- 渲染和验收：真实 FL 导出 WAV、PCM 时长/非静音检查、项目语义 diff/三方 Playlist merge，以及只读 `project validate` 预检。

## 最快入口

```powershell
uv tool install --editable . --python 3.12
flstudio doctor
flstudio project inspect --input song.flp --summary --section channels --section patterns
flstudio project validate --input song.flp
flstudio session start --project song.flp --output-dir private-worker
flstudio live --session private-worker/session.json status
flstudio session save --session private-worker/session.json --output result.flp
flstudio session stop --session private-worker/session.json
```

首次使用实时 worker 时，在 FL 的 MIDI 设置中加载随 CLI 安装的控制器并重载 MIDI scripts。之后 Agent 使用 addressed file-RPC；MIDI relay 只作为兼容路径，不需要 MCP server。

## 验证边界

本版在 FL Producer 26.1.6.5639 上完成了真实保存、重开、回读和 WAV 证据。工厂 NewStuff 工程的只读体检结果为 45 通道、8 个 Pattern、213 音符、1494 个 Playlist 项、29 条 Mixer、8 条 Automation，编码回读一致。插件、Piano Roll、录制、动态 Mixer 和 Playlist 淡化的证据保存在开发机的 `.lab/fullstack` 中，不随包发布。

CLI 不声称接管 FL 的每一个自绘插件面板，也不把未知历史 Playlist 布局当作已支持。没有 host 参数或可观察画布后置条件的任意插件控件仍需要 Agent 与 GUI 协作；未知布局会明确拒绝。参考实现的兼容性差异和已知限制见 [fullstack 文档](fullstack.md)。

## 安装

```powershell
uv tool install flstudio-cli==1.0.0 --python 3.12
```

或者从仓库安装 editable 版本；FL Studio 本体、工厂模板和第三方插件不随 CLI 分发。许可证为 MIT。

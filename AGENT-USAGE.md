# Agent quickstart / 给 Agent 的快速入口

Windows x64；本机验证为 FL Studio Producer 26.1.6.5639。Python 3.12+，安装 uv。

```powershell
git clone https://github.com/LiweiDonVee/flstudio-cli.git
cd flstudio-cli
uv tool install --editable . --python 3.12
$fl = Join-Path $env:USERPROFILE '.local\bin\flstudio.exe'
& $fl doctor
```

文件编曲无需MIDI桥、控制器脚本或MCP。默认FL安装目录为
`C:\Program Files\Image-Line\FL Studio 2026`；不同位置用build的`--template`和render/verify的`--fl-install`指定。

1. 先 `project inspect --input FILE --summary`；需要完整音符时去掉summary。 长程会话先用 `project snapshot --input FILE --focus project --focus channels --budget 12000`；响应内的 `context.omitted` 明确省略项，再按需只展开 Playlist、Mixer 或 Automation。`project validate --input FILE` 用来交付前做只读结构预检。
2. 新曲 `project build --request song.json --output NEW.flp`；已有工程 `project edit` 或 `notes replace`。格式见[请求说明](docs/quickstart-0.2.md)。
3. Pattern编号从1开始，通道/Mixer/效果槽从0开始。时间是工程PPQ的整数ticks；保存文件的pan范围±6400，live pan范围±1，都以0居中。
4. `--dry-run`只预览，不写工程、不渲染、不联系MIDI桥。输出必须是新路径，原曲不覆盖。
5. `render wav --project NEW.flp --output NEW.wav`使用实际FL引擎。非空编曲导出静音或明显截短会失败。
6. Sytrus/混音/FX 链先读 [0.5 工作流](docs/sytrus-mixing.md)，可检索音色、改音源参数、发送电平、完整效果链和常用效果器参数。build/edit 一份请求组合完成；例子 `examples/sytrus-mix.json`。
7. Emphasizer 专用音频探针：`plugin verify --project FILE --track 0 --slot 9 --param Emphasis --value .25 --output-dir NEWDIR`。交付 `NEWDIR/project.flp`，诊断probe副本不是用户编曲。其他参数用前后原生 WAV 核验。

`artifact_ready`表示保存文件回读；`verified_scopes`列出实际证据。参数验证的音频来自隔离副本和受控输入，不冒充当前GUI状态。
遇到unknown或不支持的插件状态，不把它解释成成功。

人机协作方式：GUI保存当前工程 → CLI写新副本 → GUI打开新副本继续编辑。
已有/新建有链接 Automation、逐条变长 Playlist、Audio Clip 裁切与增益见
[当前迭代](docs/fullstack.md)。文件修改不会改变当前编辑器内存。独立 worker 内可用
`piano-roll` 精确读写当前卷帘，`recording` 录制真实事件，`mixer` 扩展轨道；需要 GUI
上下文时由 Agent 截图后使用 `session input` 操作该 worker，并验证实际结果。

实时控制最快路径：`flstudio bridge install-controller`，在 FL 重载一次 MIDI 脚本后
运行 `flstudio live status`。已有 FLStudioMCP 绑定会保留；全新机器须在 MIDI Input
为一个输入选择 FLStudioCLI 控制器一次。新控制器用文件连接，不需要旧 MCP 或 MIDI relay。

独立验证用 `flstudio session start --project FILE --output-dir NEWDIR`，随后所有实时命令
加 `live --session NEWDIR/session.json`。用 `session save --session ... --output NEW.flp`
取得 FL 正式保存的副本，最后 `session stop --session ...`。不要把 private session 当用户编辑器。
`session screenshot --output NEW.png --receipt NEW.json` 后查看图像；`session input`
用该 receipt 发送 key/click/drag。只接受 CLI 自己启动的 private worker，不接管全局鼠标。
菜单用键盘选择；自绘弹出菜单的鼠标激活不可靠。输入回包的 submitted 不表示操作成功。
文件插件设置用 `plugin settings --project FILE --channel N` 或 `--track N --slot N`；
`project edit` 的 `plugin_settings` 可组合 Wrapper 标志、小插件 raw 字段及 Notebook 2 文本页。

需要旧 MIDI 传输时：`uv tool install --editable ".[midi]" --python 3.12`，再执行`flstudio bridge start`和`bridge status`。
桥由CLI自身运行，不需要旧MCP server或daemon；复用已配置的FLStudioMCP RX/TX虚拟端口及FL控制器协议。新机仍须完成FL端的一次配置。
`live status`、`live set-tempo`、`live set-mixer-pan`、`live plugin-params`、`live set-plugin-param`都可用。
音源实时参数用 `--channel N`；先 `live query --command cli_capabilities` 确认控制器版本。
通道索引为全局索引，不依赖当前 Channel Group。`plugin-find` 按名称检索；`plugin-apply`
一次请求最多 32 个参数，包含回读与失败后的条件恢复；详见 [当前迭代](docs/fullstack.md)。
普通参数事务只验证 `host_readback`；离散参数可在保存重开后归一到另一数值。
需持久化验证时用 `session verify-params --session ... --request checks.json --output-dir NEWDIR`，
按请求中的 `expect` 判定实际重开值；不重启原工作实例。
播放/停止、定位、音量、静音和其他宿主原语，用`live apply --request JSON`给出写入与独立回读条件；模板见[实时命令](docs/live-commands.md)。
`live query`可查询播放、定位、通道、插件和路由。CLI自带桥只执行控制器已有原语，不支持任意Python执行。
live写入不保存工程；修改前读原值，调试后恢复。它不是仅安装本CLI就具备的能力。

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

1. 先 `project inspect --input FILE --summary`；需要完整音符时去掉summary。
2. 新曲 `project build --request song.json --output NEW.flp`；已有工程 `project edit` 或 `notes replace`。格式见[请求说明](docs/quickstart-0.2.md)。
3. Pattern编号从1开始，通道/Mixer/效果槽从0开始。时间是工程PPQ的整数ticks；保存文件的pan范围±6400，live pan范围±1，都以0居中。
4. `--dry-run`只预览，不写工程、不渲染、不联系MIDI桥。输出必须是新路径，原曲不覆盖。
5. `render wav --project NEW.flp --output NEW.wav`使用实际FL引擎。非空编曲导出静音或明显截短会失败。
6. Sytrus/混音/FX 链先读 [0.5 工作流](docs/sytrus-mixing.md)，可检索音色、改音源参数、发送电平、完整效果链和常用效果器参数。build/edit 一份请求组合完成；例子 `examples/sytrus-mix.json`。
7. Emphasizer 专用音频探针：`plugin verify --project FILE --track 0 --slot 9 --param Emphasis --value .25 --output-dir NEWDIR`。交付 `NEWDIR/project.flp`，诊断probe副本不是用户编曲。其他参数用前后原生 WAV 核验。

`artifact_ready`表示保存文件回读；`verified_scopes`列出实际证据。参数验证的音频来自隔离副本和受控输入，不冒充当前GUI状态。
遇到unknown或不支持的插件状态，不把它解释成成功。

人机协作方式：GUI保存当前工程 → CLI写新副本 → GUI打开新副本继续编辑。
任意Automation、自绘插件控件和未知变长clip仍需GUI；文件修改不会暗中改变当前编辑器内存。

可选live：`uv tool install --editable ".[midi]" --python 3.12`安装MIDI依赖，再执行`flstudio bridge start`和`bridge status`。
桥由CLI自身运行，不需要旧MCP server或daemon；复用已配置的FLStudioMCP RX/TX虚拟端口及FL控制器协议。新机仍须完成FL端的一次配置。
`live status`、`live set-tempo`、`live set-mixer-pan`、`live plugin-params`、`live set-plugin-param`都可用。
音源实时参数另用 `--channel N`，安装 `bridge install-controller-extension` 后在 FL 重载一次 MIDI 脚本；先 `live query --command cli_capabilities` 确认全局寻址扩展已加载。此模式不依赖当前 Channel Group。
播放/停止、定位、音量、静音和其他宿主原语，用`live apply --request JSON`给出写入与独立回读条件；模板见[实时命令](docs/live-commands.md)。
`live query`可查询播放、定位、通道、插件和路由。CLI自带桥只执行控制器已有原语，不支持任意Python执行。
live写入不保存工程；修改前读原值，调试后恢复。它不是仅安装本CLI就具备的能力。

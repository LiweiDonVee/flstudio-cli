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
6. 参数需要生效证据时：`plugin verify --project FILE --track 0 --slot 9 --param Emphasis --value .25 --output-dir NEWDIR`。当前保存参数配置为Emphasizer v2 Emphasis；取用`NEWDIR/project.flp`，诊断probe副本不是用户编曲。

`artifact_ready`表示保存文件回读；`verified_scopes`列出实际证据。参数验证的音频来自隔离副本和受控输入，不冒充当前GUI状态。
遇到unknown或不支持的插件状态，不把它解释成成功。

人机协作方式：GUI保存当前工程 → CLI写新副本 → GUI打开新副本继续编辑。
任意Automation、自绘插件控件和未知变长clip仍需GUI；文件修改不会暗中改变当前编辑器内存。

可选live：先单独部署兼容的[flstudio-mcp MIDI桥](https://github.com/rosasynthesiz/flstudio-mcp)，确认本地9787与FL控制器连通；CLI直接使用该桥的TCP协议。
`live status`、`live set-tempo`、`live set-mixer-pan`、`live plugin-params`、`live set-plugin-param`都可用。
live写入不保存工程；修改前读原值，调试后恢复。它不是仅安装本CLI就具备的能力。

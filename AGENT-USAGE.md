# 给 Agent 的运行入口

本机命令：`C:\Users\Owner\.local\bin\flstudio.exe`。新版终端也可直接用 `flstudio`。
旧 Harness 进程可能还没刷新 PATH，此时使用绝对路径。

当前版本0.3。已有本机MIDI桥连通时，用 `live status` 查看正在打开的FL；
`live set-tempo`、`live set-mixer-pan` 和 `live set-plugin-param` 可直接操作当前会话。
`live plugin-params --track 0 --slot 9` 会读取插件的参数名。未回读确认的写入返回unknown；live命令不保存工程。
文件编曲/渲染仍可独立运行。新机若需要live能力，需另外部署兼容MIDI桥；它不是仅安装本CLI就具备的能力。

换机器部署：装好 Windows 版 FL Studio 与 uv，在此仓库目录运行 `uv tool install --editable . --python 3.12`，
然后 `flstudio doctor`。无需 MIDI 端口、FL 控制器脚本、旧 MCP 或测试依赖。
默认安装目录是 `C:\Program Files\Image-Line\FL Studio 2026`；不同目录用 build 的 `--template` 和 render 的 `--fl-install` 明确指定。

1. 从用户的已保存工程读取：`project inspect --input FILE --summary`；需要音符则去掉 summary。
2. 新曲用 `project build --request song.json --output NEW.flp`；格式见 [quickstart](docs/quickstart-0.2.md)。
3. 改曲用 `project edit` 或 `notes replace`，指定明确 Pattern/通道和新的 output。原曲不覆盖。
4. 预览加 `--dry-run`。此时不写工程、不生成音频、不触发 FL，不需要开启全局状态开关。
5. `render wav --project NEW.flp --output NEW.wav` 会让真正的 FL 打开并渲染；非空曲目导出静音或截短会失败。

不要再调用旧 MCP 的选通道→连续Piano Roll脚本写入。GUI当前选中项不是音符目标。
`artifact_ready` 是保存文件回读；`verified_scopes` 表明实际检查了什么。新副本需要在GUI打开后才成为人正在编辑的工程。
保存工程编辑现支持FL26的88字节固定布局Playlist；未知变长布局仍不支持。
不支持的自绘插件控件、Automation曲线或可变长度clip不能假装完成。
这些部分由人继续在 GUI 编辑：保存后让 CLI 读取该已保存副本，再用新 output 返回下一版。

现成示例：在项目目录运行 `flstudio project build --request examples/beat.json --output my-beat.flp`，
再运行 `flstudio render wav --project my-beat.flp --output my-beat.wav`。

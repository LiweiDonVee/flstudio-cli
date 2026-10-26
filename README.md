# FL Studio CLI

**0.3.0** 本地 CLI，可创建和编辑真实 FL 工程，并调用 FL 原生渲染。

实际工作流：**JSON 编曲 → 新 FLP 副本 → 逐 Pattern/通道回读 → FL 原生 WAV 渲染**。
文件编曲不依赖当前卷帘、抢焦点、快捷键脚本或 MCP。可选的 `live` 命令复用已有本地 MIDI 桥，直接操作打开的 FL。

```powershell
uv tool install --editable . --python 3.12
flstudio project build --request song.json --output song.flp
flstudio project inspect --input song.flp --summary
flstudio render wav --project song.flp --output mix.wav
```

[编曲请求格式与完整用法](docs/quickstart-0.2.md)

本机已安装到 `C:\Users\Owner\.local\bin\flstudio.exe`，并加入用户PATH。
无需重开旧Harness即可用该绝对路径调用。[给 Agent 的简短入口](AGENT-USAGE.md)。

可用功能：

- 新建多个采样/音源通道，加载本机 generator 的 `.fst` 预设。
- 明确指定 Pattern 和通道读写音符；替换一个通道时保留其他通道的原始音符记录。
- Pattern 命名，安排和重复 Playlist pattern clips。
- 修改样本路径、名称、音量、声像、通道到 Mixer 的路由。
- Mixer 音量、声像、名称、静音、编组路由；从 `.fst` 加载效果器。
- 保存到新副本；计划绑定源哈希，拒绝源变化和覆盖已有文件。
- 在独立 Windows 桌面调用真实 FL 批渲染，检查新 WAV、实际帧数及音量。
- `--dry-run` 不写工程、音频、脚本或状态文件。

```powershell
flstudio notes list --project song.flp --pattern-number 1 --channel-index 0
flstudio notes replace --project song.flp --pattern-number 1 --channel-index 0 --notes notes.json --output revision.flp
flstudio project edit --input song.flp --request changes.json --output mixed.flp
flstudio audio inspect --input mix.wav
flstudio capabilities
```

已有 MIDI 桥已连通时，还可直接修改当前会话：

```powershell
flstudio live status
flstudio live set-tempo --bpm 130
flstudio live set-mixer-pan --track 1 --value 0.25
flstudio live plugin-params --track 0 --slot 9
flstudio live set-plugin-param --track 0 --slot 9 --param Emphasis --value 0.25
```

`live` 通过已有 `127.0.0.1:9787` MIDI 桥操作宿主 API，需该桥和 FL 控制器已配置。
不启动 MCP 前端或修改端口配置；`--dry-run` 不连接桥。实际值未收敛时返回 `unknown`，没有保存工程。
保存文件的单参数修改见 [0.3 用法与验证](docs/release-0.3.md)。

写入命令操作保存的工程副本，**不会把改动偷偷写进当前打开的 GUI**。
结果中的 `artifact_ready` 证明文件已写入并回读；`fl_engine_export` 证明 FL 真正打开并导出了它。
输出文件必须是新路径；原始工程保持不变。

本机已验证 FL Studio Producer **26.1.6.5639**。新工程基于本机自带 Basic 模板；
不附带或重新分发 Image-Line 的模板/插件。
复杂编辑过的可变长度 Playlist clip、任意 Automation 曲线、任意第三方插件自绘控件和内存工程附着尚未支持，
遇到未识别的数据布局会拒绝处理。

只保留 [三个工作流回归](tests/test_workflows.py)；实际 FL 导出和独立盲测另记在 [发布验证](docs/release-0.2.md)。
当前0.3独立对比结论为[CLI略优](docs/comparison-2026-10-26.md)，尚未达到“明显更优”的GitHub发布门槛。
[架构](docs/architecture.md)和[长期覆盖目录](docs/coverage.md)是后续路线，不代表所有条目已经实现。

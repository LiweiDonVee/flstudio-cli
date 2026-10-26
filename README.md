# FL Studio CLI

独立的 **0.2.0** 本地 CLI，已能创建可由真实 FL Studio 打开和渲染的工程。

实际工作流：**JSON 编曲 → 新 FLP 副本 → 逐 Pattern/通道回读 → FL 原生 WAV 渲染**。
不再依赖当前卷帘、抢焦点、快捷键脚本或旧 MCP 进程。

```powershell
uv sync --locked
uv run flstudio project build --request song.json --output song.flp
uv run flstudio project inspect --input song.flp --summary
uv run flstudio render wav --project song.flp --output mix.wav
```

[编曲请求格式与完整用法](docs/quickstart-0.2.md)

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
uv run flstudio notes list --project song.flp --pattern-number 1 --channel-index 0
uv run flstudio notes replace --project song.flp --pattern-number 1 --channel-index 0 --notes notes.json --output revision.flp
uv run flstudio project edit --input song.flp --request changes.json --output mixed.flp
uv run flstudio audio inspect --input mix.wav
uv run flstudio capabilities
```

写入命令操作保存的工程副本，**不会把改动偷偷写进当前打开的 GUI**。
结果中的 `artifact_ready` 证明文件已写入并回读；`fl_engine_export` 证明 FL 真正打开并导出了它。
输出文件必须是新路径；原始工程保持不变。

本机已验证 FL Studio Producer **26.1.6.5639**。新工程基于本机自带 Basic 模板；
不附带或重新分发 Image-Line 的模板/插件。
复杂编辑过的可变长度 Playlist clip、任意 Automation 曲线、任意第三方插件自绘控件和内存工程附着尚未支持，
遇到未识别的数据布局会拒绝处理。

只保留 [三个工作流回归](tests/test_workflows.py)；实际 FL 导出和独立盲测另记在 [发布验证](docs/release-0.2.md)。
[架构](docs/architecture.md)和[长期覆盖目录](docs/coverage.md)是后续路线，不代表所有条目已经实现。

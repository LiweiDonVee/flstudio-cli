# FL Studio CLI

独立的 Python 3.12+ CLI，当前版本 **0.1.0 / M0**。现在可以诊断安装文件、探测保存的 FLP 容器、查看能力目录、生成音符替换计划。**目前尚不能读取实际音符、操作 FL、保存或渲染工程。**

所有命令默认输出一个 UTF-8 JSON Result，含 `schema_version: 1`；帮助、版本和错误也使用相同外层结构。计划中的 Pattern 编号与全局 Channel 索引只是未绑定的用户 selector，`executable=false`，实际应用和验证数量均为 `null`。真实 apply 入口明确拒绝并退出 7。

在本目录安装和运行（已安装 [uv](https://docs.astral.sh/uv/) 和 Python 3.12+）：

```powershell
uv sync --locked
uv run flstudio --help
uv run python -m flstudio_cli --help
uv run flstudio doctor --fl-install 'C:\Program Files\Image-Line\FL Studio 2026' --json
uv run flstudio capabilities --json
uv run pytest -q
```

本机可直接复制的诊断命令，无需将 uv 加入 PATH：

```powershell
& 'C:\Users\Owner\.cherrystudio\bin\uv.exe' --directory 'E:\WorkSpace\tools\flstudio-cli' run flstudio doctor --fl-install 'C:\Program Files\Image-Line\FL Studio 2026' --json
```

`doctor` 只读取 FL64/FLEngine 文件版本、SHA-256 与工具发现信息，不启动 FL。`flp probe` 只验证 `FLhd/FLdt` 边界和稳定文件哈希，notes、patterns、playlist 始终报告 `unavailable`。有多个安装时必须用 `--fl-install` 选择。

默认不创建 state、log、MIDI、工程或计划文件；`notes replace --dry-run` 和 `plan build` 共享纯计划函数。只有显式 `--plan-out` 可以创建指定的新计划文件，父目录必须已存在，已有文件一律不覆盖。CLI 没有旧 MCP、9787 端口、控制器或原生桥依赖。

- [实际命令与完整示例](docs/commands.md)：含合成容器、请求与示例计划的生成方法。
- [M0 验收记录](docs/m0-verification.md)：本机只读基准、离线测试和准确限制。
- [架构与决策](docs/architecture.md)、[阶段实施计划](docs/implementation-plan.md)、[功能覆盖矩阵](docs/coverage.md)、[调查与来源](docs/research.md)。

M1 的五通道创作、Playlist、保存重开和真实 WAV 渲染仍在规划中。外部项目或旧系统的证据不表示新 CLI 已支持这些操作。

# FL Studio CLI：新项目规划

本目录于 2026-10-26 新建，目前只有架构与实施规划，没有产品代码、已安装后端或可运行命令。此次调查没有操作正在运行的 FL，也没有修改旧 MCP、其部署或 PR 工作树。

目标是独立的 FL 专用 CLI：统一音符、Pattern、Playlist、混音、插件、样本、Automation、保存和渲染；AI 与人操作同一个工程时，明确对象、状态和结果。GUI 能做的事情是长期覆盖目标，具体支持以逐功能、逐版本验收记录为准。

推荐采用 Python 3.12 CLI 和操作日志，组合官方 MIDI Scripting API、可选 FruityLink 原生桥、FLP 文件观察器及 Windows GUI 后端。CLI 的命令契约、对象定位和验证由本项目负责；旧 MCP、MacroCLI、OpenCLI 都不作为必需运行时。

- [架构与决策](docs/architecture.md)：后端、对象、会话、dry-run、事务与未知结果。
- [功能覆盖矩阵](docs/coverage.md)：现有证据、开发路径和真实 FL 验收。
- [实施计划](docs/implementation-plan.md)：首个端到端切片、阶段门和工程文件职责。
- [调查与来源](docs/research.md)：固定提交、官方文档、版本限制和本机证据。

**M0 是第一批可立即实现的工作**：独立 CLI、doctor、只读 FLP 容器探测、能力目录和无副作用 plan/dry-run；真实 apply 明确拒绝。M0 不需要 PyFLP、FruityLink 或旧 MCP 运行。

**M1 是第一个完整创作切片**：新建隔离工程 → GUI 自动加载五个样本通道 → 自动导入五组 MIDI → 按 channel/pattern 回读 12/8/37/6/8 个音符 → Playlist → 保存/重开 → 由 FL 渲染并检查 WAV。它不运行旧 Piano Roll 写入脚本，也不依赖尚未公开的 FruityLink 0.1.26 安装包。若 FL 26 的 FLP 回读尚不能可靠完成，切片保持未通过，不降级为“发送成功”。

当前本机目标是 `C:\Program Files\Image-Line\FL Studio 2026\FL64.exe`，FL64 和 FLEngine 均为 `26.1.6.5639`。新 CLI 当前所有功能均处于“待实现”；旧系统的验证只用于选择后端和设计回归用例。

真正影响后续路线的两项决策：是否部署并适配 FruityLink 的进程内桥；将来是否允许发布包含 GPL PyFLP 的发行物。建议先完成不改 FL 安装目录的 GUI/API 基线，在私有实验中验证 FLP 读取；这两项不阻碍命令契约和隔离验收环境的开发。

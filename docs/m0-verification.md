# M0 验收记录

日期：2026-10-26。版本：flstudio-cli **0.1.0**。范围：实施计划任务 0.1–0.5，单独新仓库与 `.venv`。未启动、关闭或操作 FL，未修改旧 MCP、其脚本或用户工程。M1–M5 保持未实现。

## 环境与构建

- Python 3.12.10 / Windows x64，解释器为本项目 `.venv\Scripts\python.exe`。
- uv 0.11.16；实际生成的 `uv.lock` 锁定 Click 8.5.0、Pydantic 2.14.1、pytest 9.1.1 及其依赖。产品只依赖 Click/Pydantic。
- `uv sync --locked`、`uv lock --check` 成功；`uv build` 生成 `dist/flstudio_cli-0.1.0.tar.gz` 和 wheel。依赖未装入旧系统环境。
- console script `flstudio` 与 `python -m flstudio_cli` 均经真实子进程执行。所有业务输出、帮助、版本和已覆盖错误均为 UTF-8 JSON，stderr 不混入业务输出。

## 离线行为测试

`uv run pytest -q`：**80 passed**。普通 pytest 只运行离线测试，不启动 FL，没有自动 live hook。

测试先运行于缺失实现上，确认失败，再实现并复跑。覆盖重点：

- Unicode 原样往返、嵌套非 finite 数值的字段路径、正零规范化；严格整数拒绝布尔/字符串/浮点（含 0.0）、范围约束、未知字段、重复 JSON key、过深 JSON、超出解析器限制的整数；异常应用错误仍为结构化 JSON。
- 合成 FLhd/FLdt 的有效边界、错误 magic/长度/格式/PPQ、截断、尾随数据、超大声明长度；有界版本读取和未知首事件；真实读期间追加、读后删除导致源变化失败，不提供可用 snapshot hash。
- doctor 缺失安装、缺失引擎、无效 PE 版本资源、多个候选需选择、目录发现、Windows console launcher 的真实路径。
- 同输入稳定计划、只接受同一源的容器证据、selector 未绑定、四项未满足能力、实际计数为 null；纯规划函数在 resolve/stat/open 全部被阻断时仍成功。
- 安装后的真实 CLI 子进程：help/version、doctor、probe、capabilities、两个共用规划入口、结构化错误与退出码、两个 apply 入口明确拒绝 7。
- 默认 dry-run/build：临时 HOME/USERPROFILE/APPDATA/LOCALAPPDATA/state/scripts/logs 和输入文件树哈希不变；子进程在导入应用前加载 audit hook，进程/网络 gateway 和旧系统/MIDI/UI 自动化导入被阻断。启动 CLI 的父进程不在阻断范围内。
- 显式 plan-out 只创建指定的新文件并报告副作用；已有文件（包括源 FLP、请求和已有计划）不覆盖；缺少父目录不会隐式创建目录。

## 本机只读验收

```powershell
uv run flstudio doctor --fl-install 'C:\Program Files\Image-Line\FL Studio 2026' --json
uv run flstudio flp probe --input 'E:\WorkSpace\tools\flstudio-mcp-local\piano-roll-lab\probe-base.flp' --json
uv run flstudio capabilities --json
uv run flstudio notes replace --project 'E:\WorkSpace\tools\flstudio-mcp-local\piano-roll-lab\probe-base.flp' --pattern-number 1 --channel-index 0 --notes 'tests\fixtures\notes-one.json' --dry-run --json
```

doctor 返回 `verified`，scope 只有 `environment_files`：

| 文件 | FileVersion | SHA-256 |
| --- | --- | --- |
| FL64.exe | 26.1.6.5639 | b8006e980c58b3d3a7899ab9edffa8f7701c5eed9fc0dade1899bf639d80866c |
| FLEngine_x64.dll | 26.1.6.5639 | bc3637c3e41694c820865e757d88a42bdc15b6db4011582a2ef8f4d1b05a2d95 |

真实 probe 返回 `partial / semantic_reader_unavailable`，退出 0，scope 只有 `flp_container`。size 53208；FLhd length 6、format 0、channel_count 5、PPQ 96；FLdt 声明/实际 53186；首事件 199，有界长度 12，producer version `26.1.6.5639`。源文件验收前后 SHA-256 都为 `3d7476bf24bd7e0b94ed92612b138ad843c66f33ac9dd6ea0b76c9fdd5dba4ab`，文件未写入。

自身验收脚本运行九条真实 CLI 命令：help/version、doctor、真实 probe、capabilities、真实源 notes dry-run、合成源 plan build、两个拒绝 apply；退出码分别符合 0 或 7。只读结果保存在本项目忽略目录 `.superpowers/verification/`，示例计划是 `.demo/plan.json`，其输入为自行合成的 36 字节容器。没有提交用户 FLP 或工厂样本。可复现示例见 [commands.md](commands.md)。

主代理另用安装后的 `.venv/Scripts/flstudio.exe` 独立运行七条验收：doctor、真实 probe、capabilities、notes dry-run、plan build、两个 apply 拒绝。子进程 audit hook 禁止 socket 网络/连接、子进程和文件写入/创建/rename；只放行 `platform.platform()` 读取本机名称所需的 `socket.gethostname`。七条均返回有效 JSON、stderr 为空；输入和独立临时 HOME/APPDATA 文件树哈希不变，两个规划入口输出相同 Plan。独立原始记录：`C:\Users\Owner\AppData\Local\Temp\flstudio-cli-m0-3c8e90d491d84397a425221a8f697f3b\parent-acceptance.json`。

## 边界与实施决定

最终独立审查确认唯一错误输出缺陷已修复：重复 key 含孤立 Unicode surrogate 时，
诊断只转义 key 的显示文本，CLI 返回 `invalid_json`、退出 2、stderr 为空，不改变有效输入数据。
该修复提交为 `920712a593711d6edb9ab490d44632558ae3982b`。修复后主代理复跑完整 80 项测试，
并在上述只读 audit 环境增加该非法输入，最终八条安装后 CLI 验收均通过；输入与用户目录树仍不变。

Result 与 Plan 都用版本化、extra=forbid 的 Pydantic 契约。规范化编码用于输出和请求 hash；输入校验保留原数值类型，防止负浮点零先被规范化成可接受的整数。Plan 的 source_sha256 绑定本次稳定容器观察，request_sha256 绑定排序后的规范化请求。

FLP probe 只流式验证容器和有限版本前缀，不遍历其余事件。Windows Python 3.12 的 path.stat/fstat 对旧 ctime 字段可能语义不同，因此跨 API 比较身份、大小、mtime，同类 API 分别比较前后 ctime。检测到变化会撤销观察；这不是并发编辑下的原子快照保证。

capabilities 只有 doctor、flp.container、plan 标为 implemented/available，验证级别为 offline_fixture；外部候选证据单独列出，所有 live 操作仍是 not_implemented/source_only。没有 GUI/native/MIDI 后端空类。

计划明确 `executable=false`、`target_resolution=unresolved_selectors`、`bound_target=null`；未满足 `score.semantic_read`、`target.resolve`、`notes.replace`、`project.persistence_verify`。artifact/applied/verified count 均为 null，只有 requested_count 来自输入数量。没有实际写入、保存或音频验证证据，不能宣称创作闭环通过。

默认 stdout 是唯一计划产物。显式 plan-out 采用新文件独占创建，拒绝覆盖，父目录必须已存在；该文件副作用另外报告。未建立日志库、broker、端口、脚本、注册表或 GUI 会话。两个真实 apply 入口在读取请求/计划前拒绝，退出 7。

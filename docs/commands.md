# M0 命令

在项目根目录执行 `uv sync --locked`。Python 最低 3.12，console script 为 `flstudio`，`python -m flstudio_cli` 调用同一个入口。

每次调用在 stdout 输出一个 UTF-8 JSON Result（包括 `--help`、`--version`、错误）；`--json` 可省略。`data.help` 是可读帮助文本。stdout 不混入日志。字段 `schema_version` 当前为整数 1。

| 命令 | 当前行为 | 退出码 |
| --- | --- | --- |
| `flstudio --help` / `--version` | 输出帮助 / CLI 版本 | 0 |
| `flstudio doctor [--fl-install DIR]` | 只读文件版本、哈希、运行解释器与 PATH 工具发现 | 0；多个候选未选择时 2；源变化或 I/O 失败时 5 |
| `flstudio flp probe --input FILE` | 只读容器边界、头字段、哈希、可确认的 producer version | 有效容器 0；损坏、截断、源变化或不可读时 5 |
| `flstudio capabilities` | 已实现能力与外部研究证据分开列出 | 0 |
| `flstudio plan build --request FILE [--plan-out FILE]` | 校验请求和源容器，生成不可执行计划 | 0；输入校验失败 2；文件 I/O / 容器失败 5 |
| `flstudio notes replace --project FILE --pattern-number N --channel-index N --notes FILE --dry-run [--plan-out FILE]` | 与 plan build 共用规划 | 同上 |
| `flstudio notes replace ...`（无 `--dry-run`） | 拒绝，`backend_unimplemented`；不读取请求文件或派发 | 7 |
| `flstudio plan apply --file FILE` | 拒绝，`backend_unimplemented`；不读取计划或派发 | 7 |

语法错误（未知命令、缺少必需参数等）退出 2。缺少后端不影响“查询/规划已完成”的退出码：例如有效容器可以返回 `status=partial`、`reason_code=semantic_reader_unavailable`、退出 0；计划可以 `status=planned`、`reason_code=backend_unimplemented`、退出 0。不得把这种结果解释为 FL 已改变。库层拒绝无效观察证据；对应 CLI 错误使用退出 3。

## 只读诊断和探测

```powershell
uv run flstudio doctor --fl-install 'C:\Program Files\Image-Line\FL Studio 2026' --json
uv run flstudio flp probe --input 'C:\Music\song.flp' --json
uv run flstudio capabilities --json
```

doctor 不运行 FL 或 `dotnet --version`。`tools.dotnet.discovered=true` 仅表示找到了 PATH 命令，不表示 .NET 9 SDK 就绪。实际运行的 Python 在 `runtime.executable`，PATH 中 Python 在 `tools.python.path`；文件版本通过 Windows version.dll 的文件 metadata API 读取。指定安装不完整或未找到安装时仍是完成的诊断，以 partial、null 和原因表示缺口。`verified_scopes` 仅为 `environment_files`。

容器探测使用小端 `FLhd` 头（六字节 payload），要求紧随其后的 `FLdt` 声明长度等于实际剩余字节。头格式只接受 project/score 的 0/1，PPQ 不得为 0。只有 FLdt 第一事件为 199、32 位有界且规范的 VLQ、长度不超过 64 字节、有效的四段 ASCII 数字版本加 NUL 时才给出 `producer_version`；其余为 `unknown` 并给出原因。它不继续解码工程事件，不证明整个事件流语义有效。头中的 `channel_count` 也不代表已枚举 live 通道。

探测流式计算 SHA-256，只保留小段前缀用于版本判断；比较路径与文件句柄的身份、大小和纳秒修改时间，以及同类 API 的前后 ctime。变化会撤销整个观察，不返回可用哈希。它是变化检测，不提供文件系统原子快照或排除恶意恢复 metadata 的保证。`verified_scopes` 只有 `flp_container`，三个语义区段均为 `unavailable`，不会用空数组冒充没有对象。

## 生成合成示例和计划

以下代码由使用者显式创建 `.demo` 中的演示文件，不启动 FL。合成文件只用于容器验收，不是可演奏的完整 FL 工程，也不包含用户歌曲。`.demo` 已被 Git 忽略。

```powershell
@'
import json, struct
from pathlib import Path
root = Path('.demo')
root.mkdir(exist_ok=True)
version = b'26.1.6.5639\0'
data = bytes([199, len(version)]) + version
blob = struct.pack('<4sIhHH', b'FLhd', 6, 0, 5, 96)
(root / 'container.flp').write_bytes(blob + struct.pack('<4sI', b'FLdt', len(data)) + data)
request = {'operation':'notes.replace', 'project':str((root / 'container.flp').resolve()),
           'pattern_number':1, 'channel_index':0,
           'notes':[{'key':36,'start_tick':0,'length_tick':24,'velocity':100}]}
(root / 'request.json').write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
'@ | uv run python -

uv run flstudio notes replace --project '.demo\container.flp' --pattern-number 1 --channel-index 0 --notes 'tests\fixtures\notes-one.json' --dry-run --json
uv run flstudio plan build --request '.demo\request.json' --plan-out '.demo\plan.json' --json
uv run flstudio plan apply --file '.demo\plan.json' --json
# 最后一条预期退出 7。已有 plan.json 不能覆盖，重新示例时指定新的输出名。
```

`--notes` 读取 NoteInput 数组；`--request` 读取上例完整对象。相对路径按调用时工作目录解释，进入请求模型后解析成绝对路径。Pattern 从 1 起，全局 Channel 索引从 0 起；M0 不验证这些 selector 是否对应真实对象。

音符使用整数 ticks，key 0..127、start_tick ≥ 0、length_tick > 0、velocity 1..127。数值不接受布尔、字符串或浮点自动转换；即使 `0.0` 也不是整数 tick。多余字段、重复 JSON key、NaN、±Infinity、溢出到无穷的数值均拒绝；错误包含字段路径。输出数值零统一为正零，原始 Unicode 不做二次转码。空 notes 列表可表达未来清空意图，仍不可执行。

计划的主要字段如下（实际 JSON 还包含完整请求与两项 SHA-256）：

```json
{
  "schema_version": 1,
  "executable": false,
  "target_resolution": "unresolved_selectors",
  "bound_target": null,
  "unmet_requirements": ["score.semantic_read", "target.resolve", "notes.replace", "project.persistence_verify"],
  "effects": ["live_score_replace", "project_persistence"],
  "requested_count": 1,
  "artifact_count": null,
  "applied_count": null,
  "verified_count": null
}
```

`effects` 是未来应用意图，未实际发生。Result 的 `data.file_effects` 记录本次真实文件副作用：默认 `[]`，显式输出后为 `[{"kind":"plan_file_created","path":"绝对路径"}]`。计划文件本身是裸 Plan JSON；stdout 仍是 Result，内含同一个 `data.plan`。输入哈希和请求哈希使用同一份排序键、UTF-8、finite/正零编码逻辑。

`--plan-out` 只创建明确指定的新文件，不递归创建父目录，也不覆盖已有文件、源 FLP 或请求。M0 不建立 broker、日志库、MIDI 端口或 live 会话，不写脚本、注册表、启动项、设置或 UI。`plan build` 会只读观察源容器；核心 `build_plan(request, source_probe)` 只消费这份观察，不访问文件系统或执行网关。

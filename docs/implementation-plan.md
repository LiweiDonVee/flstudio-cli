# FL Studio CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This document does not authorize installing a native bridge or editing a user song; follow the active task's authorization and scope.

**Goal:** 先交付完全独立、可运行、如实描述能力的 FL CLI；然后交付五通道创作、保存重开与真实渲染闭环，逐步扩大到 GUI 功能目录。

**Architecture:** Python CLI 调用同一个类型化应用内核。首里程碑只有只读诊断、FLP容器探测、能力证据与无副作用计划；后续 live/GUI/native/file 后端均通过显式能力和结果验证接入，不依赖旧MCP运行或生命周期。

**Tech Stack:** Python3.12、uv、Click、Pydantic、pytest；M0只需文件/系统读取。M1再加入Windows GUI、MIDI产物和FLP语义观察器。SQLite/broker在需要live会话时加入。FruityLink与PyFLP都不是M0必需依赖。

**Spec:** `E:\WorkSpace\tools\flstudio-cli\docs\architecture.md`，配套 `coverage.md`、`research.md`。

## Global Constraints

- Windows x64；首个已知目标 `26.1.6.5639`，不能把其余FL2026版本视为等价。
- 独立根目录 `E:\WorkSpace\tools\flstudio-cli`，独立venv、依赖、配置、状态目录和进程；不导入/启动/停止旧MCP代码、daemon、venv或controller。
- 不修改 `E:\WorkSpace\tools\flstudio-mcp`、`flstudio-mcp-local` 或 `flstudio-mcp-upstream-pr`；只读证据可以引用。
- M0 不启动FL、不向FL发送请求、不连接旧9787端口、不创建MIDI端口、不安装脚本、不改注册表或FL设置。
- dry-run 不触发UI、FL mutation、artifact准备、save或implicit state/log file写入；仅显式 `--plan-out` 可写计划文件。
- `requested_count`、artifact_count、applied_count、verified_count 分开；未知/未写入不能填 requested_count。
- FLP容器有效不等于音符/Playlist解析成功；缺少语义读取时必须标 unavailable，不能返回空数组冒充零对象。
- 不使用 hosted web_search。依赖安装和所有构建只在新项目中进行。

---

## M0：第一批可立即实施的工作

M0 是用户可运行的CLI，不是全创作工具。完成标准：`doctor`、`flp probe`、`capabilities`、`plan build`、`notes replace --dry-run`可运行；真实apply明确拒绝；每条输出准确区分“容器检查/生成计划”与“FL实际改变”。

### 文件布局与责任

```text
pyproject.toml                         # flstudio console entrypoint、Python3.12、独立依赖
uv.lock                              # 实际解析出的依赖锁
src/flstudio_cli/__init__.py          # 产品版本
src/flstudio_cli/__main__.py          # python -m flstudio_cli
src/flstudio_cli/cli.py               # Click命令树、错误到退出码
src/flstudio_cli/contracts.py         # Result/Request/Plan/Capability模型
src/flstudio_cli/json_output.py       # UTF-8、finite检查、正零规范化
src/flstudio_cli/environment.py       # 只读doctor与Windows文件版本查询
src/flstudio_cli/flp_probe.py         # FLhd/FLdt容器、hash、有限version提取
src/flstudio_cli/capabilities.py      # 操作目录、来源、当前availability
src/flstudio_cli/planning.py          # 纯计划生成，不含执行器
tests/test_contracts.py
tests/test_flp_probe.py
tests/test_planning.py
tests/test_cli.py
tests/fixtures/notes-one.json         # 一条明确tick音符的请求数据
docs/commands.md                     # 只记录实际已实现命令
```

M0不建立占位的GUI/native类假装已有后端，也不预装.NET、PyFLP、MacroCLI、OpenCLI。测试fixture可由测试代码构造二进制，避免分发用户FLP或工厂样本。

### Task 0.1：可执行入口与结果契约

**Files:** `pyproject.toml`、`src/flstudio_cli/{__init__,__main__,cli,contracts,json_output}.py`、`tests/test_contracts.py`、`tests/test_cli.py`。

**Interfaces:**

```python
class Result(BaseModel):
    schema_version: Literal[1] = 1
    command: str
    status: Literal["planned", "artifact_ready", "verified", "partial", "unknown", "needs_human", "rejected", "failed"]
    reason_code: str | None = None
    verified_scopes: list[str] = []
    data: dict[str, Any] = {}

def encode_result(result: Result) -> str: ...  # 拒绝NaN/Infinity，所有数值0规范化
def main() -> None: ...                       # console script入口
```

以上为接口规格，不要求逐字复制可变默认值写法；实现使用Pydantic field default factory。具体业务count放入对应data模型，不用通用 `ok` 推断mutation。

- [ ] 建立独立Python3.12环境，console script为 `flstudio = flstudio_cli.cli:main`；`python -m flstudio_cli`调用同一入口。
- [ ] 先写契约测试：中文参数名正确UTF-8往返；`-0.0`序列化为0；NaN、±Infinity返回含字段路径的明确错误；unknown不能出现虚构applied_count。
- [ ] 实现契约/JSON输出；日志走stderr，stdout JSON可被标准`json.loads`完整读取。
- [ ] 验证 `uv run flstudio --help`、`uv run python -m flstudio_cli --help`、`uv run pytest tests/test_contracts.py tests/test_cli.py -q`。
- [ ] 在新仓库已初始化且无无关改动时提交这批文件；未初始化仓库由主代理决定初始化，不改父目录或旧仓库。

### Task 0.2：只读环境 doctor

**Files:** `environment.py`、`cli.py`、`tests/test_cli.py`、`docs/commands.md`。

**Interfaces:** `inspect_environment(fl_install: Path | None) -> Result`。data包含当前CLI解释器/版本、平台/位数、可执行入口、指定或检测到的FL64/FLEngine路径和FileVersion、engine SHA-256、工具可发现性与后端状态。版本/路径未知用null加原因。进程运行状态不是该M0命令必需条件。

- [ ] 用临时目录测试：未安装FL、仅有FL64无engine、无有效PE version、两个安装路径必须显式选择；都不启动任何文件。
- [ ] 实现Windows文件版本资源读取；文件hash读取即可，不运行FL.exe来查版本。可运行Python的路径与PATH上的python分开显示。
- [ ] doctor将GUI/native/MIDI标为not_configured或not_implemented；输出“存在dotnet命令”不能写“.NET9 SDK已就绪”。
- [ ] 验证命令与本机文件版本一致，并确保退出/输出能够区分诊断完成与某能力未可用。

```powershell
uv run flstudio doctor --fl-install 'C:\Program Files\Image-Line\FL Studio 2026' --json
```

预期：FL64/FLEngine=`26.1.6.5639`，engine SHA与research R9一致；`verified_scopes=["environment_files"]`；无live FL支持声明。

### Task 0.3：只读 FLP 容器探测

**Files:** `flp_probe.py`、`cli.py`、`tests/test_flp_probe.py`、`docs/commands.md`。

**Interfaces:** `probe_flp(path: Path) -> Result`。data含absolute path、size、sha256、header format/channel_count/ppq、data chunk声明长度与实际长度、可确认的producer version、parse_scope=`container`、semantic_sections状态。`channel_count`来自header，不声称已枚举真实live channels。

- [ ] 测试先覆盖有效容器、FLhd长度错误、截断FLdt、畸形version长度、未知首event、文件读取中变化。
- [ ] FLhd读取使用明确的小端结构 `struct.Struct("<4sIhHH")`：magic、header length、format、channel count、PPQ；核对FLdt与声明长度，不反序列化未知工程事件。
- [ ] 若FLdt第一个event恰是199且长度编码/ASCII版本满足边界，提取producer version；否则版本为unknown。禁止在任意二进制字符串里搜索版本并假装结构化解析。
- [ ] 不继续走未认证的event172/Playlist解析。notes/patterns/playlist始终 `unavailable`，不返回伪造0。容器成功仅 `verified_scopes=["flp_container"]`。
- [ ] stat前后确认输入没变；若变化返回 `source_changed`，不声称hash和结构属于同一快照。
- [ ] 验证合成fixture及只读本地probe-base文件；源文件sha256前后相同。

用于测试的真实可执行fixture构造规格：

```python
version = b"26.1.6.5639\0"
data = bytes([199, len(version)]) + version
blob = struct.pack("<4sIhHH", b"FLhd", 6, 0, 5, 96)
blob += struct.pack("<4sI", b"FLdt", len(data)) + data
```

```powershell
uv run flstudio flp probe --input 'E:\WorkSpace\tools\flstudio-mcp-local\piano-roll-lab\probe-base.flp' --json
uv run pytest tests/test_flp_probe.py -q
```

真实文件是只读输入；测试产物全部在pytest临时目录。producer version如果无法可靠提取可以unknown，不需改解析器来迎合某个样本。

### Task 0.4：能力目录和纯计划

**Files:** `capabilities.py`、`planning.py`、`contracts.py`、`cli.py`、`tests/test_planning.py`、`tests/fixtures/notes-one.json`。

**Interfaces:**

```python
class NoteInput(BaseModel):
    key: int                 # 0..127
    start_tick: int          # >=0
    length_tick: int         # >0
    velocity: int            # 1..127，0另按明确语义支持

class NotesReplaceRequest(BaseModel):
    operation: Literal["notes.replace"]
    project: Path
    pattern_number: int      # >=1，仍是未解析的用户selector
    channel_index: int       # >=0，全局索引selector
    notes: list[NoteInput]

class Plan(BaseModel):
    schema_version: Literal[1] = 1
    request: NotesReplaceRequest
    source_sha256: str
    executable: bool
    unmet_requirements: list[str]
    effects: list[str]
    requested_count: int

def list_capabilities() -> list[dict[str, Any]]: ...
def build_plan(request: NotesReplaceRequest, source_probe: Result) -> Plan: ...
```

- [ ] `notes-one.json`采用 `[{"key":36,"start_tick":0,"length_tick":24,"velocity":100}]`。验证非法key、负tick、0长度、无穷值、pattern0、负channel在规划前拒绝。
- [ ] capability至少列出notes read/write、pattern、Playlist、mixer、plugin、automation、save、render；明确current implementation与external evidence不同，M0只有doctor/flp.container/plan是已实现。
- [ ] `build_plan`是纯函数，输出 `executable=false` 及 `score.semantic_read`、`target.resolve`、`notes.replace`、`project.persistence_verify` 等未满足项；只凭header不假装绑定channel/pattern。
- [ ] `plan build --request request.json`和 `notes replace ... --dry-run`共用同一入口。`notes replace`不带dry-run、`plan apply`始终返回 `rejected/backend_unimplemented` 和退出码7，不连接任何进程。
- [ ] `--dry-run`输出requested_count，applied_count/verified_count为null，verified_scopes无live。`--plan-out`未提供时不创建任何文件或状态目录；提供时只创建该计划文件并报告这项文件副作用。
- [ ] 测试同输入输出稳定、input文件不变、无broker/控制器import、无进程或网络调用。规范化JSON/hash计算共享编码逻辑，不依赖Python dict偶然顺序。

```powershell
uv run flstudio capabilities --json
uv run flstudio notes replace --project '.\tests\fixtures\container.flp' --pattern-number 1 --channel-index 0 --notes '.\tests\fixtures\notes-one.json' --dry-run --json
uv run flstudio plan apply --file '.\plan.json' --json
```

`container.flp`由测试/验收临时生成，不提交冒充真实FL工程；示例执行时先放到指定fixture路径或替换为实际临时路径。最后一条必须明确拒绝执行；plan文件需要显式 `--plan-out`生成，不能由dry-run暗中写出。

### Task 0.5：首里程碑验收与交付

**Files:** `tests/test_cli.py`、`README.md`、`docs/commands.md`，必要时新增只读验收报告 `docs/m0-verification.md`。

- [ ] 使用真实CLI子进程执行help、doctor、flp probe、capabilities、notes dry-run和拒绝apply；stdout都是有效JSON，非零状态与原因一致。
- [ ] 在临时独立HOME/APPDATA/state目录运行dry-run，前后文件树hash一致；同时拦截所有执行gateway的调用并断言为0，防止只测“没有save”。
- [ ] 普通pytest只运行离线测试，不启动FL；不增加任何自动运行live测试的默认hook。
- [ ] `uv run pytest -q`及上述CLI验收通过后更新README：清楚列出“可诊断/探测/规划；尚不写FL”。记录新CLI自己的version、解释器和依赖锁。
- [ ] 交付一条可复制运行命令和一个示例计划；不要以M0通过宣称五通道闭环完成。

## M1：五通道真实往返垂直切片

这才是第一个自动创作闭环。它不依赖未公开FruityLink bundle，也不直接重写FLP。首选G执行、F独立观察；M后端在成熟操作上可接入。若F语义读取未通过，M1不能发布，M0仍可正常交付。

### M1新增文件与接口

```text
src/flstudio_cli/sessions.py              # owned/attached、epoch、写租约、进程身份
src/flstudio_cli/journal.py               # SQLite操作状态、operation_key/request hash
src/flstudio_cli/execution.py             # preflight/dispatch/readback/reconcile
src/flstudio_cli/observations.py          # snapshot来源、范围、一致性与冲突
src/flstudio_cli/backends/windows_gui.py  # 精确窗口/操作/后置条件
src/flstudio_cli/backends/flp_snapshot.py # 只读语义parser适配、未知字段状态
src/flstudio_cli/artifacts/midi.py        # 独立MIDI生成与解析验证，无tempo event
src/flstudio_cli/rendering.py             # owned FL渲染、文件与音频验证
src/flstudio_cli/profiles/fl_26_1_6_5639/ # GUI宏/profile与能力证据，非通用坐标
tests/live/test_five_channel_roundtrip.py # 仅显式live运行
tests/live/test_interruption.py           # 未知结果/用户操作/取消，隔离工程
```

后端接口固定为：`inspect(target) -> Observation`、`preflight(plan) -> Readiness`、`execute(step, context) -> DispatchReceipt`、`observe_post(step) -> Observation`。DispatchReceipt只描述派发/回执，不含未经验证的success；`verify(expected,before,after) -> Verification`由核心处理。reconcile读取journal而非重新执行step。

### Gate 1：建立隔离fixtures和FLP语义观察器

- [ ] 只在新建lab目录和获准控制的测试FL会话创建：空工程、两个通道各一音符、重叠duplicate notes、重排/删除后的channels、多个patterns、Pattern/Audio/Automation clips、含trim/fade/stretch的clips。
- [ ] 记录实际GUI中已知内容、FL保存文件、Windows/FL/DPI/语言、engine hash；不使用用户当前歌曲作为可修改fixture。
- [ ] 评估PyFLP固定revision及必要patch或独立reader；使用真实FL26保存的文件检测长度/未知event/完整消费。不在产品默认安装中无条件引入未决定许可的GPL组合。
- [ ] 对每类fixture精确读回已知notes/channel IID/pattern/clip；不支持的字段明确unknown。无修改往返如进行，必须新文件且FL重开不变；读取通过不自动开放写入。
- [ ] gate证据不足则保留M0、继续解析器适配，不用截图/count代替score验证。

### Gate 2：一个通道到两个通道，消除旧错误触发条件

- [ ] GUI后端先实现新工程/open/save-as，按PID/HWND绑定；失焦、弹窗、不匹配DPI拒绝动作。
- [ ] 加载两个自生成短WAV为Sampler并明确唯一名字；对每个导入前确证pattern和目标editor绑定。故意先打开另一个channel的Piano Roll，验证宏能重新绑定而非只选Channel Rack。
- [ ] MIDI导入只在预期空score进行；第一个版本不承担既有复杂score无损replace。每次导入后FL保存快照，F观察全部目标channels：期望通道的完整note delta准确，其他通道不变。
- [ ] 第一次出现错误目标、未知结果或UI卡住立刻停止该run，保留before/after和截图；禁止重复快捷键。不得为复现旧挂死对用户工程连续注入脚本。

### Gate 3：五通道完整验收

固定测试工程：130 BPM、4/4、从FL读取PPQ；5个唯一命名Sampler、5份本地生成短样本、pattern1、4小节。五组notes数为12/8/37/6/8，总71；使用互异key/time/velocity序列。它是新的合成验收曲，不是事故丢失音乐的恢复。

- [ ] 先dry-run，验证工程snapshot/样本/MIDI产物/焦点均不变，write gateway计数0。
- [ ] 显式prepare生成五份MIDI，解析核对notes且无tempo event；结果只报artifact_ready。
- [ ] apply依次导入，每次保存并比较五通道完整multiset，不累计“requested”代替actual。记录operation_key和dispatch边界。
- [ ] 在Playlist明确track/start/length安排pattern；需要重复时铺多个clips，不把伸长clip当循环。
- [ ] 保存新路径after.flp；受控关闭/重开owned项目；再次读回notes、归属、Pattern、Playlist、tempo、PPQ和sample路径。
- [ ] 由FL渲染新WAV；先用已认证的render profile固定sample rate/format/tail/song range，再用官方命令行触发。不能只用/Ewav假定全部选项默认正确。
- [ ] 无tail的4小节130 BPM参考duration为 `16 * 60 / 130 ≈ 7.384615s`，按实际采样率检查frames及有限容差；检查五个声部的预设独立活动区、静音对照和播放抽听，不能用非零RMS冒充所有声部正确。
- [ ] 重复执行相同operation_key不新增notes/clips。模拟在派发后丢回执：返回unknown；reconcile识别已完成/partial，不重放。
- [ ] 两次冷启动、错误焦点和一次人打断场景都通过；每次实际FL/engine hash一致。失败证据保留，修复后只重跑受影响场景。

交付目录应包含request/plan、before.flp、after.flp、reopened-observation.json、完整note/clip diff、mix.wav、audio-check.json和evidence.json。证据记录源文件hash及修改范围，不包含用户无关工程内容。

## M2：常用编辑与协作会话

- 独立official_midi控制器/broker：只读nonce握手、实际回包端口识别、build校验、全局channel索引、MIDI连接诊断；使用本项目独立端口/脚本目录，不复用旧服务。
- 逐条加入tempo、transport、mixer/channel controls、routing、宿主plugin参数；每项setter有readback和单位测试，新增插件需save/reopen/audio验收。
- 增加既有工程attached模式、明确GUI控制权与snapshot能力；结构变更/用户编辑使refs失效，保存后的FLP与live冲突阻断下一次写入。
- 加入插件加载/卸载、preset、sample替换的G profiles；超时检查实际实例状态，避免重复加载。

验收：旧MCP完全不运行时，新CLI独立完成这些操作；旧MCP在旁运行时也没有共享端口/目录/配置冲突。用户重启FL后doctor明确报告连接和build，不能沿用旧会话。

## M3：FruityLink原生后端的独立兼容项目

- 拿到可复现匹配host/bootstrap，或在明确授权后开发独立部署；安装/恢复路径先记录，不能拿公开0.1.8顶替0.1.26。
- 补.NET9/CMake/MSVC工具链只发生在需要该后端时；PythonCLI与private CPython运行时分开。
- 按完整FLEngine5639 hash验证symbols/layout，从只读query到单一setter，再到一音符/多通道、clip、Automation；每项结果与F快照比较。
- 通过后替换相应G执行路径，复用M1全部语义验收；保留backend来源和不支持项。原生可用不意味着Sampler高级设置、channel delete/reorder、任意preset全支持。
- 如live/saved notes不同，停止支持升级并记录缺页/过滤/slot/load-time语义；不能挑一个count作为真相。

## M4：扩展编排、Automation与插件适配

独立增量：audio clip trim/fades/stretch；多Arrangement；Automation首次link/linear points到高级曲线/多目标；Sampler高级设置；FX链状态保持的移动/复制；常用第三方plugin profiles。每个增量重复“明确目标→执行→live+保存→实际声音”的门，不把未实现项目一次性装进CLI help冒充可用。

## M5：GUI覆盖目录与分发

完成按工作流枚举的覆盖目录、版本profile更新机制、用户可复现diagnostic包和安装/卸载；再加MCP薄适配、可选视觉agent及插件profile扩展。通用GUI动作只描述动作，已认证语义command才报告工程成功。选择发行许可后处理PyFLP/GPL与SDK/插件许可证；不要用子进程分隔当许可结论。

长期“GUI全覆盖”验收是目录中每个操作都有实现、定位、观察和版本证据；没有一个有限测试集能证明任意未来插件/未知控件全部可靠。

# FL Studio CLI 架构设计

日期：2026-10-26。状态：供评审的设计，不代表实现或兼容认证。证据编号见 [research.md](research.md)，功能边界见 [coverage.md](coverage.md)。

## 1. 目标和范围

**产品目标**：把 FL 的可操作对象变成可发现、可组合、有真实结果证据的 CLI。人可以在 GUI 中创作，AI 可以读工程并执行明确的命令；双方改变工程后重新建立对象映射。

**长期目标**：对 GUI 工作流建立完整的操作目录；可用 API 负责结构化修改，文件处理负责离线转换与观察，GUI 负责没有接口的功能。任意第三方插件的任意控件只有“可尝试 GUI 操作”的理论可达性，不能由此宣称已验证支持。支持率按具体操作、FL build、插件版本、显示配置统计。

**分阶段范围**：M0 是Windows x64/Python3.12的可运行CLI，只有诊断、FLP容器探测和计划，不写FL。M1再面向 FL Studio Producer `26.1.6.5639`、交互桌面、单个写会话，完成五通道样本编曲、Pattern/Playlist、保存/重开、WAV 渲染；常用混音编辑随后加入。先让新工程流程全自动完成，再扩大到任意既有工程。

**首版非目标**：macOS；无 GUI/headless 保证；任意 FLP 的通用重写；任意插件的所有自绘控件；运行任意进程内 Python/eval；替换音频引擎；从 71-note 事故恢复遗失旋律；宣称旧挂死根因已解决。独立 MIDI 导出是有用的产物能力，但不等于 FL 音符写入能力。

## 2. 方案比较及选型

| 方案 | 优点 | 决定性限制 | 结论 |
| --- | --- | --- | --- |
| 仅官方 MIDI API / 旧 MCP 包装 | 基础读状态、混音和参数已有本机证据 | 没有通用跨通道 Piano Roll/Playlist CRUD；继承旧桥边界 | 不作为新产品架构 |
| 全部押注 FruityLink 原生桥 | 类型化音符、clip、Automation、插件操作最接近完整控制 | 精确 build/ABI 依赖；完整 bootstrap 不在公开源码；新安装包未公开；本机 5639 未验证 | 重点候选，逐能力接入 |
| 独立命令内核 + 多后端 + 单一验证契约 | 可先交付 GUI 闭环，原生后端成熟后可替换；证据与动作分开 | 需要开发 FL 专用定位、观察和验收，工作量真实存在 | **采用** |

Python 3.12 + Click 负责 CLI，Pydantic 负责 JSON 契约，标准库 SQLite 保存会话/操作日志。常驻本机 broker 负责会话租约、顺序执行和 MIDI 生命周期；CLI 每次调用不持有隐式全局 dry-run。首先只支持一个 FL 写会话，不建分布式服务。未来 MCP 只是同一应用服务的薄适配器，不另写一套业务逻辑。

```text
flstudio CLI / future MCP
        │ typed request + explicit session + operation key
        ▼
Command catalog → snapshot / resolve → execution plan
        │                                 │
        │                    capability/profile decision
        │                                 ▼
        │              official_midi | fruitylink_native
        │              flp_file      | windows_gui
        │                                 │
        └────────── verifier ◀──────────────┘
                     │ live state + saved FLP + rendered audio
                     ▼
          operation journal + truthful result + artifacts
```

## 3. 后端与路由

### official_midi：官方 API 的明确子集

独立的新控制器脚本和协议；不把旧 MCP 进程当内部依赖。可迁移经授权且许可允许的算法，但每个操作重新过新契约和本机验收。用于 transport、tempo、全局通道枚举、mixer、宿主暴露的插件参数，以及实际存在的 Pattern/track 属性。版本通过握手读取 API 版本及 controller 内容哈希；不能把 FL 主版本当 API 版本。

索引适配显式使用 `globalCount` / `useGlobalIndex`，不把 Channel Rack 当前分组的相对索引当全局对象。官方 `getGridBit/setGridBit` 是步进网格，不是任意 Piano Roll score；`triggerLiveClip` 是触发，不是 Playlist clip 新建接口。[R3]

MIDI 握手对计划中的请求口发送随机 nonce，并在已配置候选回包口监听、按协议/nonce/build 精确识别实际回包口，记录端口全名与系统 ID。重连重新握手，不凭 RX/TX 文本推断方向，也不静默修改 FL 设置。不能取得唯一回包则 `connection_unverified`。只读握手是否在该 FL/API 配置下可工作也要实测；不能把多口监听写成既成修复。更新后 server、broker、controller 三方 build 不一致则禁止写入。

### fruitylink_native：高覆盖候选，按能力启用

直接使用 MIT SDK 或其受支持外部端点，独立实现 CLI 适配器；不复制 PolyForm Noncommercial 的 Fl-MCP 代码。SDK 源码含 host/bridge，但完整 installer/bootstrap 不在公开项目；公开 v0.1.8 不能视作当前文档所述本地 0.1.26。[R5]

启用条件是：有可复现安装/移除过程；匹配 host/native/Python 内容哈希；本机 FLEngine 的完整版本和 SHA-256；对应 operation 的 symbols/layout 能力；真实小工程读写、保存重开和音频验收。识别 scanner family、编译通过或 `IsAvailable` 为真都不足以打开全部写能力。

初步候选包括 `AddNotesAsync`、`QueryNotesAsync`、`AddPatternClipsAsync`、`CreateAutomationClipAsync`、插件加载、SaveCopy。适配器必须收紧底层允许的 `pattern<=0=current` 等隐式选择，命令外层永远要求确定目标。SDK 已说明取消 batch 可能留下前缀，Automation 创建可能残留 channel，查询分页计数是 raw slots，并有 live/saved 音符总数不一致的记录。[R6] 因此仍由本项目决定是否完成。

### flp_file：先读取，后受限写入

第一阶段只读明确保存的快照，取 patterns、channel IID、note records、Playlist 引用、插件状态块、样本路径等可正确解析字段。文件版本、数据长度、完整消费、未知记录和警告都进入结果；不把解析失败/跳过当空集合。

PyFLP 作为候选解析器而非已通过的兼容层：master 存在 Python 3.12、FL26 event172 和新版 Playlist 记录的开放兼容 PR；无公开通用 add/remove collection API。[R7] 私有实验可比较补丁分支；不能把上游 PR 的结论硬编码到全部文件。首门是本机生成的 fixtures 读回和无修改往返，特别覆盖变长/裁剪/淡入淡出 clip；不靠“长度能整除 80”猜格式。

后续写入只针对已认证的字段和模板，保留未修改 event 的原始 bytes 与顺序；输入永远不覆盖，输出写入新文件。离线文件已改并不代表 live FL 已改。只有受控打开、FL 再次保存及独立读回通过后，才声明 FL 接受该变更。禁止对运行中 FL 当前路径直接离线改写。

### windows_gui：真实原生应用适配

在获得桌面控制权时，先绑定 PID/进程启动时间/HWND/窗口所有者，再检查 modal、焦点、DPI、尺寸、语言和 FL 版本。常规对话框用 Win32/UIA；自绘 FL 控件用按窗口坐标归一化的视觉锚点、菜单/快捷键与截图后置条件；复杂第三方插件另建 profile。固定屏幕坐标不成为默认定位方式。

每个宏是有限步骤的 FL 操作：`open_piano_roll_exact`、`import_midi_to_score`、`load_sample_channel`、`place_pattern_clip`、`save_as`、`render_dialog`。宏返回“执行观测”，只有 verifier 能给出成功。字幕/OCR/标题只能帮助定位，音符归属要以保存的 score 或可靠原生读回验证。用户操作、焦点丢失或未识别弹窗会暂停计划并重新观察，不继续盲发快捷键。

MacroCLI 可参考其 Backend/Context、宏参数、前后置条件、录制和证据结构；不直接采用其默认优先级、未知条件放行及任意失败重试。所有前后置条件必须注册并可执行；未知条件使计划拒绝。[R2]

### 路由规则

每个 capability 记录操作、backend、读/写范围、版本 profile、前置条件、持久化/音频验证要求和最近证据。规划时优先选择有当前 profile 实证且变更面最小的路径；文件模式、live 模式和 GUI 模式不能无声互换。

请求派发前发现后端不可用可以重新规划，并向调用方返回新的执行路径。派发后失败或超时禁止自动换后端重做。先判断 effect；未知结果进入 reconcile。原生失败后改 GUI 点一次可能重复写入，因此不使用通用“重试直到 success”。

## 4. 命令、状态和对象

建议可执行名 `flstudio`，以下是面向完整产品的待实现契约示例；M0的精确可运行子集和离线 `--project/--pattern-number/--channel-index` 选择器见implementation-plan，不把未绑定selector当live对象handle：

```powershell
flstudio doctor --json
flstudio capabilities --session s1 --json
flstudio session start --workspace E:\FL-CLI-Lab\run-001 --template empty
flstudio session attach --pid 1234
flstudio project inspect --session s1 --refresh --json
flstudio objects list --session s1 --kind channel --json
flstudio notes replace --session s1 --pattern pat_1 --channel ch_kick --input kick.json --dry-run
flstudio plan apply --session s1 --file plan.json --operation-key beat-001
flstudio operation inspect --id op_001 --json
flstudio operation reconcile --id op_001 --json
flstudio project snapshot --session s1 --output E:\FL-CLI-Lab\run-001\after.flp
flstudio render wav --session s1 --output E:\FL-CLI-Lab\run-001\mix.wav
```

命令组：`session`、`project`、`channel`、`pattern`、`notes`、`playlist`、`mixer`、`plugin`、`sample`、`automation`、`transport`、`render`、`plan`、`operation`、`capabilities`。`--json` 输出版本化结构；文本输出为同一结果的展示，不从日志文字反向解析业务状态。

**会话**含 FL PID + start time、engine hash、broker/controller build、ownership=`owned|attached`、project path/title/untitled、session epoch、观察版本、是否允许 GUI 控制。owned 是 CLI 启动的隔离工程；attached 是用户已有工程。只有 owned 进程可以由 CLI 完成关闭/重开/命令行 render 生命周期；attached 渲染先创建明确快照并在可验证的独立 worker 上执行，不能终止用户 FL。首版 worker 如与现有 FL 的单实例/音频行为冲突，返回 `needs_human`，不强行复用用户进程。

FL 没有已确认可靠的 project generation ID。路径相同、同名 untitled 不能证明同一内存工程；外部开工程、重启、结构变化、观察断档都使 handles 过期。附着模式严格要求每个 mutation 刷新相关状态，并在取得控制权期间执行；无法排除用户编辑竞态时不宣称事务隔离。[R6]

**对象引用**由 `session_epoch + kind + registry_id + observed_revision` 组成。registry_id 是本工具的临时 handle，不冒充 FL 永久 UUID。引用携带后端定位证据：global channel index/已验证 IID、pattern 编号、arrangement、track、plugin instance fingerprint、slot、parameter index。每次结构修改后重新枚举并重建映射。

- 名称只用于搜索和显示；重名返回候选，禁止默认第一个。
- 新增/删除/重排 channel、mixer、FX 后，所有受影响索引失效；用结构 fingerprint 和原生可靠标识重定位，无唯一匹配则拒绝。
- Note 定位为 pattern/channel + key/start/length + 完整已读字段与 occurrence。重复重叠音符无法唯一定位时，要求显式 `all_matches` 或重新选定，不假造 note ID。
- Clip ref 含 arrangement、source、track、start/length 和观察版本；结构修改使 raw slot 过期。
- 插件参数名保持原始 Unicode，索引和插件身份是定位主键；重复名、未确认编码和插件替换要求重查，不模糊匹配后直接写。

**单位**：时间以 project PPQ 的整数 ticks 为执行基准，CLI 可接受明确的 quarter-note beats 并报告换算/舍入；time signature 变化通过 tempo/meter map 处理。MIDI channel、Rack channel、pattern、Playlist track、mixer slot 各自有类型，禁止隐式互换。插件 `normalized`、宿主 raw int、display text 分开保存；没有实证转换时不提供虚假的 dB/Hz 值。普通 MIDI 默认 key 0..127；FL 扩展音域另列 capability。

## 5. 执行、dry-run 和恢复

所有写入口使用同一条管线：`validate → observe → resolve → preflight → plan → dispatch → readback → persist/verify → report`。每条变更记录 effect scope，包括临时 UI 选择、文件、插件/全局设置；不把“恢复了”当没发生过。

`--dry-run` 在 dispatch 之前返回可执行计划，不点击 GUI、不切 pattern/channel、不写 score、不保存工程、不创建 MIDI/FLP、不改脚本/注册表/启动项。允许已有只读连接上的查询；若连接初始化本身有副作用，计划标为 needs_observation，不偷偷建立。stdout 是默认产物；仅显式 `--plan-out` 可以写用户要求的计划文件。逐请求 dry-run 位贯穿所有适配器，服务端再检查一次；不能靠进程中的开关，也不能采用“只是不保存”的语义。

`prepare` 是独立的有文件副作用命令，可生成 MIDI 等产物。结果为 `artifact_ready`，明确 `applied_count=null`，不表示已导入。组合计划以 after-state 描述目标，`operation_key` 与规范化请求 hash 绑定。

**事务不是数据库原子事务**。官方 API、原生桥、GUI 都可能部分成功，FL undo 未覆盖所有宿主/插件操作。每个 batch 标出可逆 setter、结构编辑、文件产物及生命周期步骤，并为支持的字段记录 before-state。owned session 在有保存能力时创建 before.flp；attached session 要求已验证 SaveCopy 或明确 save-as 流程，不能用可能改变用户工程身份的 Ctrl+S 冒充快照。

失败后，只有“当前状态仍等于本操作 after-state 且 before-state 可恢复”的 setter 才允许条件补偿；结构编辑首选保留失败副本和 before 快照，显式恢复 owned 工程。不能自动 Ctrl+Z N 次，也不能把任意 plugin 状态恢复视作无副作用。`rollback` 自身是一条可计划、可失败、需验证的操作。

**重试与结果未知**：

1. journal 在派发前持久化 operation ID、request hash、目标、preconditions 与 expected delta；同 key 同 hash返回已有状态，同 key 不同 hash拒绝。
2. 同一 FL session 只有一个写租约；每步只派发一次。只读查询可在明确无 mutation 后重试。
3. 断线、deadline、进程挂死或取消只证明调用结束，不证明原生操作未发生。置 `unknown`，禁止任何自动 append/retry/后端替换。
4. reconcile 按完整 note multiset、clip 引用和参数值比较 before/after。完全等于目标则补记 verified；部分一致为 partial；无法辨认保留 unknown。应用前未收到回执但日志也未持久化，是无法消除的 exactly-once 缺口，不能仅凭 UUID 宣称严格恰好一次。
5. 继续执行必须先确认上一 mutation 已停止或 drain 完成；取消不等于原生 UI 线程已释放。attached 挂死时只收集已有日志、进程信息和可用快照，不自动终止 FL。

## 6. 观察与成功条件

三种观察独立存储：live API snapshot、FL 保存的文件 snapshot、渲染音频。意图 manifest 不是实际工程状态。字段附 `source`、`observed_at`、snapshot hash、已知范围和缺失字段；多个来源冲突则标记 conflict，不选择好看的数字。

分页必须跟随 `next_offset` 到结束，即使过滤后当前页为空；记录 raw slots 与 matches 两种 count。请求前后观察结构 fingerprint；若变化使分页不一致则 snapshot 无效。FruityLink query 本身非原子，连续两次相同不等于有全局锁。

写音符以逐 pattern/channel 的完整 multiset 验证 key/start/length/velocity，以及支持的 mute/pan/pitch/slide 等字段；count 相等只是必要条件。修改部分字段时其他字段应保存。保存后重新打开，再由独立 FLP reader/原生 getter比对。若不能读全高级属性，命令的 preservation 只能覆盖已知字段，不能声称无损替换整个 score。

参数写入须新请求读回，允许 plugin settle，但不只比较宿主缓存；对初次支持的 plugin/preset 还要保存/重开和音频行为检验。Preset 文件 hash 不证明插件实际接受了它。Automation 还必须验证目标 link 和可预期的音频包络。渲染必须验证输入 snapshot、归属 PID、输出 freshness、完整解码、format、frames/duration、有限样本及预期有声/静音区域；文件非空或 renderer exit 0 不足以证明音乐正确。

结果采用明确状态，不复用单个 `ok` 承担所有含义：

```json
{
  "schema_version": 1,
  "operation_id": "op_001",
  "status": "unknown",
  "backend": "windows_gui",
  "session_epoch": "epoch_1",
  "requested_count": 12,
  "artifact_count": 12,
  "applied_count": null,
  "verified_count": null,
  "verified_scopes": ["midi_artifact"],
  "reason_code": "reply_timeout_after_dispatch",
  "evidence": ["artifacts/op_001/before.json", "artifacts/op_001/input.mid"],
  "next_action": "operation reconcile --id op_001"
}
```

状态集：`planned`、`artifact_ready`、`verified`、`partial`、`unknown`、`needs_human`、`rejected`、`failed`。查询/计划/prepare 按各自契约完成可 exit 0；apply 只有全部要求的验证通过才 exit 0。建议非零：2 无效/拒绝，3 前置条件或 stale ref，4 needs_human，5 执行失败且确定未成功，6 partial/unknown，7 后端/版本不支持。`verified_scopes` 明确区分 artifact、live、saved、reopened、audio。

JSON UTF-8，输出中所有 0 规范化为正零；NaN/Infinity 直接报带字段路径的错误。保留原始参数名和显示值，已证实的编码修复限定在对应适配器/profile；不能全局对所有中文二次转码。[R1]

## 7. 可发现性与覆盖维护

`capabilities` 对每项返回 `implemented`、`availability`、`verification_level`、`backend`、`profile`、`limitations`、`last_evidence`。verification_level 为 source_only / offline_fixture / live / persistence / audio；GUI 使用独立 `requires_desktop`，不把 GUI-assisted 自动等同于需人。发布状态可展示 verified-supported、verified-gui、experimental、unsupported、human-required，但底层保留这些正交字段。

新增功能先写具体 contract 与验收 fixture，连上真实 FL 后才能升级 supported。FL/插件/驱动或显示 profile 改变时失效相关认证，不直接继承“FL2026 supported”。标准 CLI 输入确定工作流；高级 `ui inspect/act` 可以扩大探索范围，但未有语义后置条件的通用动作始终只报告 executed/unverified。

## 8. 需要拍板的重大选择

1. **是否引入版本相关的进程内 FruityLink 桥。** 推荐保留适配并优先调查可复现部署，拿到匹配 bundle/5639 profile 后只在隔离工程验收。它能显著降低 GUI 依赖，但属于安装及原生兼容工程；本次规划不安装、不注入、不替换用户 FL。
2. **将来的分发许可。** PyFLP 为 GPL-3.0，Fl-MCP 为 PolyForm Noncommercial，FruityLink SDK 为 MIT。建议 CLI 自有代码独立、SDK 可复用、Fl-MCP 仅读架构；PyFLP 先作私有研究观察器。公开/商业分发前选择接受 GPL 组合发行的义务，或开发经独立实现与审阅的解析器。单独子进程或可选插件并不自动消除许可问题。

其余决定已在本设计给出默认：Python3.12、Windows、单写会话、逐请求 dry-run、先 GUI 闭环、FLP 先读后写、原生桥按能力激活、MCP 后加。无需为这些常规选择反复询问。

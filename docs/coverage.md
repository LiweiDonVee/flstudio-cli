# 功能覆盖与验收矩阵

当前未发布分支的支持与缺口以 [fullstack.md](fullstack.md) 和 `flstudio capabilities` 为准；
包括有链接 Automation、逐条变长 Playlist、第三方宿主参数、独立 FL 会话、工程字段和语义合并。
下面保留早期版本的验收及研究记录，不代表当前状态，也不将外部源码当作本机实测。

| 新 CLI 当前操作 | implemented / availability | 本项目验证范围 | 限制 |
| --- | --- | --- | --- |
| doctor | true / available | offline_fixture；本机 environment_files | 只读文件 metadata、SHA-256 和依赖发现，不查询 live FL |
| flp.container | true / available | offline_fixture；本机 flp_container | 仅 FLhd/FLdt，notes/patterns/playlist unavailable |
| plan、notes replace dry-run | true / available | saved_score目标和源SHA | 没有output路径时不可执行；不修改GUI |
| notes read/replace、pattern、playlist、mixer、采样/预设加载、save copy | true / available | 保存文件回读；真实FL打开和音频验收 | 仅已支持文件布局，非live附着 |
| render wav | true / available | 实际FL原生批渲染/PCM检查 | 独立Windows桌面，输出为新文件 |
| live attach、任意插件UI、通用automation曲线 | false / not_implemented | 外部候选证据 | 仍需适配，明确不支持 |

CLI `capabilities` 的 `verification_level=offline_fixture` 表示该实现的离线测试等级。此次本机文件读取另外记录在验收报告中，不升级为 live/persistence/audio 证书。没有 GUI/native 后端占位类或隐式旧系统依赖。

后端缩写：M = 官方 MIDI Scripting API；N = Realynx FruityLink 原生桥候选；F = FLP 文件处理；G = Windows GUI。F 第一阶段为读取保存快照，写入另行验证。N 当前本机 5639 均未验证，现有 live 记录主要来自 5570。

| 功能 / 操作 | 已有证据与边界 | 推荐实现与回读 | 升级为支持的真实 FL 验收 |
| --- | --- | --- | --- |
| 工程身份、版本、tempo、transport 查询 | 旧系统已读到本机版本/tempo/channel/mixer；project path/dirty 信息不完整 [R1] | M + 进程身份 + G；N 可提供 project path，但 untitled 不是 dirty | 同路径重开、同名 untitled、进程重启后拒绝旧 handles；查询不改工程 |
| Tempo / transport 设置 | 旧系统有 dry-run 和基础 setter 路径，非所有状态组合均实测 | M 优先；N/G 备用；每步读回 actual mode/playing | 切歌/切 pattern mode、play/stop、值设定各自读回，保存后 tempo 保留 |
| 任意 Piano Roll 音符读取 | 旧 sys 共享回执探针 available=false；M grid 不是任意 score [R1,R3] | F 快照观察；N 分页 query 候选；G 仅作定位辅助 | 对比 FL 原生保存的多 pattern/channel fixtures，完整遍历含空过滤页；不把未解析当 0 |
| 任意音符新增 / append / replace | 旧系统只验证五份 MIDI 文件 12/8/37/6/8，未自动写 FL；N 暴露 batch API [R1,R6] | 首版 G 自动单通道 MIDI 导入 + F 回读；N 合格后优先；F 写入受限模板后加入 | 故意打开另一通道卷帘后仍正确归属；逐通道 multiset 比对；保存重开；取消后无重复 |
| 音符删改 / quantize / transpose | 旧挂死根因未定，不能继续使用 shortcut+pyscript 流程；N 有 surgical edit/delete | N 逐字段修改；G 内置操作须保存前后 score 检验；F 已认证字段可补充 | 只改目标；重复同 key/start 的音符明确歧义；pan/slide/release 等未改字段保留 |
| FL 特殊音符属性 | Piano Roll API 文档含 slide、porta、color、pitchofs、repeats 等 [R4]；MIDI 不能全保留 | N 当前 typed read 不全；F/G 逐属性适配；pyscript 仅独立研究 | 特殊属性逐项 FL 保存/重开/播放；不可把 MIDI replace 标为完整 score 无损 |
| Step Sequencer 网格 | M 文档有 get/setGridBit，受当前 Pattern 与全局索引影响 | M + 明确 pattern precondition；保存 F 观察 | 在 grouped/reordered channels 中读写正确格，其他 score 不变 |
| Pattern 枚举、命名、选择、长度 | M 有相应接口，但 selected pattern 不等于非空 patternCount；旧证据中 current=1,count=0 | M/N；F 验证；内部显式一基编号 | 空 Pattern、非连续编号、重名、current 但未物化状态正确；不猜 count+1 |
| Pattern 创建、复制、删除 | N 有 create/clone，但 clone 文档只保 notes；PyFLP 无通用 collection CRUD [R6,R7] | G 基线；N 逐项；F 写入非首版 | 保留/不保留的 metadata、automation、name/color 明示；删除 clip 引用处理正确 |
| Playlist track 名称、颜色、mute | M 暴露部分 track 控制；不等于 clip CRUD | M/G；N typed tracks；F 保存比对 | 一基 Playlist 与零基 mixer/channel 不串号；重开保持 |
| Playlist Pattern clips 增/删/移/长度/重复 | N 有接口；clip raw index 变动会失效；伸长 clip 不保证循环播放 [R6] | G + F 为首切片；N 优先候选；repeat 明确铺多个实例 | 轨道、pattern、起止 ticks 精确；四小节重复四段都有声，禁止只延长一段冒充循环 |
| Playlist Audio clips、trim/fade/stretch/make unique | N 文档有部分缺口；PyFLP 新记录/变长格式存在开放问题 | G 专用操作；F 读回 source/trim 在格式认证后启用 | 对含裁剪、淡化、拉伸的实际 FL 保存再读，音频边界/连续性正确 |
| 多 Arrangement、markers、time signature | N 有 arrangement CRUD；M 有 markers/部分 meter API | M/N/G；F 按 arrangement 读取 | 同名不同 arrangement 不串目标；tempo/meter map 与渲染长度一致 |
| Mixer 音量、pan、mute/solo、名称 | 本机旧系统枚举和部分同值 setter 通过；不代表新 dB 模型准确 [R1] | M；N raw units 严格映射；G 验证特殊状态 | 左右声道/静音行为、范围和单位；保存重开，不误动 Master/Current |
| Channel → mixer、sends、sidechain | M 可 route；N active sends 与 level=0 有区分，sidechain 标记仍有缺口 [R3,R6] | M/N 认证的路由；sidechain 用 G 后置检查 | 路由拓扑和实际 stem；断开与静音不同；插入 mixer 后重新定位 |
| Mixer 插入、重排、FX 链移动/复制 | N 有插入 live 记录，但 clone effect 曾仅按名字重新加载而不保状态 [R6] | N 逐项/G；F 比对 effect state 和 routing | 插入前后的插件状态、sends/channel routes不变；复制保持 preset/params 才算成功 |
| 加载 generator / effect、移除和重排 channel | M 无通用完整 loader；N AddChannel/FX load 存在，delete/move仍有 GUI 缺口 | G 精确 loader；N 认证后替换；新对象重新枚举 | 插件身份/版本、channel/slot、数量与可发声状态；加载弹窗和超时后不重复加实例 |
| 已加载插件参数枚举/设置 | 旧系统本机中文参数名和 dry-run 定位有证据；宿主暴露参数不等于所有 UI 控件 | M/N；按 instance + index；原始 Unicode、raw/normalized/display 分开 | 两个同名实例不串写；中文/重复名；参数值另请求读回、保存重开及有代表性音频变化 |
| 插件 preset / state 加载、保存、复制 | N 某些 VST3/native格式有5570记录，专有 .SerumPreset 可静默无效；.fst 路径不同 [R6] | N 已证实格式/G plugin profile；文件 hash 与状态 hash 分开 | 插件接收了状态、参数/音色变了；同 preset 重载一致；重开保持；不以调用返回判成功 |
| 样本发现、加载、替换、路径依赖 | 旧 MCP 主要由人工加载；N 有 sample loader，live 原路径 query存在缺口 | G/N；F 已保存路径 + 文件 SHA；本地文件验证 | 使用路径/文件内容正确，重开无 missing；不能用 session 历史冒充实际当前路径 |
| Sampler reverse、trim、fades、stretch、envelope | N 明确部分不是 REC 事件；Sampler 不等于 hosted plugin 参数 [R5,R6] | G；若用户请求的是离线处理则 F/audio 处理输出新 WAV，不悄悄替代语义 | GUI 实际控件/保存属性/音频三者一致；替换样本与非破坏性 FL 设置分开支持 |
| Automation Clip 创建、首次参数 link、placement | N 有创建/首次 link/placement；失败可能留下 channel；M 参数写不是 clip [R6] | N 认证后或 G 工作流；F 验证 target link+points+clip | 正确参数对象；创建后重开仍链接；渲染前半有声后半静音的已知包络 |
| Automation 点、曲线与一条曲线多目标 | N replace 限 2..4000 linear points，curve=0；额外目标链接未暴露 | N 支持的线性子集；G 高级曲线/多目标；F 读回后认证 | 不是只比点数；时间/值/tension/curve/链接都核对，seek 后等待参数 settle |
| 保存、Save As、SaveCopy、重开 | N 有接口且拒绝 orphan notes；G 可做本机基线；完整安装路线仍有缺口 | G 首版；N 合格后用 SaveCopy；F 观察 | 真正新文件、freshness/hash；重开后内容相等；attached 身份是否改变准确报告 |
| WAV 渲染、格式/尾音/范围/stems | FL 官方有 /R /E /O，未在此规划实跑；N 本身只是打开 export dialog，Fl-MCP 才有编排 | owned worker调用 FL 批渲染；G 配置未暴露选项；音频解码验证 | PID/输入 snapshot/格式/帧数/范围/尾音/有声区一致；失败和取消保留工程；不得重用旧 WAV |
| Edison、NewTime/NewTone、复杂音频编辑 | 本调查无可用通用结构化后端证据 | G 按工作流适配；输出音频文件验证；可自动化范围单列 | 实际波形/处理范围、导出和工程引用正确；每工具逐流程认证 |
| 第三方自绘插件任意控件 | UIA 和参数 API 都可能不可见；视觉可达不等于可靠 API | G 插件版本 profile + 图像锚点/可选视觉 agent；缺乏后置条件则 unverified | 不同 DPI/窗口大小/插件版本；识别 modal/加载状态；实际参数/state/音频回读，否则 human-required |

## 支持标签的发布规则

- **verified-supported**：该 build 的实现、对象定位、live readback和所需 persistence/audio 证据齐全。
- **verified-gui**：同样达到验证要求，但依赖交互桌面和对应显示/语言 profile；可全自动执行，不等同人工操作。
- **experimental**：有实现或外部实测，可在隔离 fixture 使用，当前本机 profile 未过完整门。
- **unsupported**：接口/实现/可靠定位缺失，明确拒绝。
- **human-required**：当前环境出现未覆盖弹窗、无法识别控件或无法取得桌面控制权，返回具体停点与证据。

覆盖分母不是“命令总数”。每项按 read / write / persist / audio 与版本矩阵统计，例如参数写支持而专有 preset 不支持，不能合并成“插件已全覆盖”。“执行一次成功”先记单次 evidence；同一个 fixture 冷启动、重复运行与失败路径验证通过后才升级发布标签。

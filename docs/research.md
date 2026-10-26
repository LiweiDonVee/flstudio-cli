# 调查来源与证据边界

调查日期：2026-10-26。只读源码/本地证据/官方文档调查；未调用 hosted web_search、未操作 live FL、未安装依赖或桥接。外部 README 的已支持声明不等于本机验证。

## R1. 旧部署与事故证据

本地来源：

- `E:\WorkSpace\tools\flstudio-mcp-local\README.md`
- `E:\WorkSpace\tools\flstudio-mcp-local\AGENT-DEPLOY.md`
- `E:\WorkSpace\tools\flstudio-mcp-local\CLI-ANYTHING-ASSESSMENT.md`
- `E:\WorkSpace\tools\flstudio-mcp-local\piano-roll-lab\STATUS.md`
- `E:\WorkSpace\tools\flstudio-mcp-local\fix-verification.json`
- `E:\WorkSpace\tools\flstudio-mcp-local\fix-server-verification.json`
- `E:\WorkSpace\tools\flstudio-mcp-local\note-handoff-verification.json`
- `E:\WorkSpace\tools\flstudio-mcp-local\piano-roll-lab\probe-readback.json`

记录支持：本机 5639 的 ping、tempo、channel/mixer 枚举、中文参数修复和有限 setter/dry-run 验证；独立五份 MIDI 的 71-note 文件级验收。音符交付结果明确 `ok=false, verified=false, applied_count=null`。未证明自动跨通道写入恢复，也未确定两次 UI 挂死的原生根因。

读到的源码 `fl_controller/FLStudioMCP/device_FLStudioMCP.py` 提供 channels/mixer/plugins/patterns 等调用，帮助识别官方 API 路线；本任务没有改其文件。`probe-readback.json` 证明该次控制器未收到 score 回执且实际回包到 RX；不能据此证明解释器一定隔离。

## R2. CLI-Anything 与 MacroCLI

现场确认本地 `E:\WorkSpace\tools\CLI-Anything` HEAD：`34f519533bc175d2fe287ab8316b0dd99bb9cc43`，Apache-2.0。

- [HARNESS.md](https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/cli-anything-plugin/HARNESS.md)：CLI 构建方法、真实应用输出验收。
- [README](https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/README.md)：源码可得性限制对闭源 FL 相关。
- [MacroCLI routing.py](https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/macrocli/agent-harness/cli_anything/macrocli/core/routing.py)：默认优先级实际为 native_api=100、gui_macro=80、visual_anchor=75、file_transform=70、gui_agent=60、semantic_ui=50；按 availability 回退，配置 retry 会重复 execute。不是 FL 操作语义的安全路由器。
- [runtime.py](https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/macrocli/agent-harness/cli_anything/macrocli/core/runtime.py)：未知 condition 返回通过；process 检查缺依赖也可能放行。必须替换为可验证的 FL 条件。
- [semantic_ui.py](https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/macrocli/agent-harness/cli_anything/macrocli/backends/semantic_ui.py)：有 Windows/pywinauto 分支，但不能据此证明 FL 自绘控件可见。
- [visual_anchor.py](https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/macrocli/agent-harness/cli_anything/macrocli/backends/visual_anchor.py)：`_get_window_bounds` 当前实现 Linux/macOS，Windows 需补。
- [auto-save-dry-run.md](https://github.com/HKUDS/CLI-Anything/blob/34f519533bc175d2fe287ab8316b0dd99bb9cc43/cli-anything-plugin/guides/auto-save-dry-run.md)：不保存的 dry-run 定义不能用于 live FL 的无副作用保证。

可复用：命令发现/帮助、backend interface、宏参数、前后置条件结构、追踪和真实产物测试。不能复用为“已完成”的部分：FL target binding、score/Playlist读取、Windows锚点、任意失败重试、FL专用后置条件。此次未安装或运行 MacroCLI。

## R3. 官方 MIDI API 与命令行渲染

- [MIDI Scripting](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm)
- [Save/Export 与 command-line options](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/fformats_save_export.htm)

本次 HTTP 读取核对了 get/setGridBit、globalCount/useGlobalIndex、channels.getChannelIndex、setTargetFxTrack、plugins.get/setParamValue、general.safeToEdit/isModified/getRecPPQ、patterns 属性和 Playlist track/live-trigger 功能。在线手册列各函数引入的 MIDI API 版本，可能新于已安装构建，必须 runtime capability 探测。

官方渲染语法包括 `/R[filename] /E<extensions> /F<foldername> [project.flp]` 及 `/O<foldername>`。/R 是渲染工程；格式如 /Ewav。手册示例用 FL.exe，本机实际选择 FL64.exe；不能未经实测宣称它是 headless 或支持全部渲染参数。渲染仍须受控进程和音频验证。

## R4. 已安装 Piano Roll API

`C:\Program Files\Image-Line\FL Studio 2026\System\Config\Piano roll scripts\Piano roll script reference.txt` 现场读取。

`flpianoroll.score` 暴露当前 score 的 PPQ、noteCount、get/add/deleteNote、markers；Note 有 number/time/length/pan/velocity/release/color/pitchofs/slide/porta/muted/selected/repeats 等。支持 preview 的脚本用 createDialog/apply。文档未提供从外部按任意 pattern/channel 获取 score 的控制器 API，也未证明共享 sys 对象。新产品不依赖这个未经证明的桥。

## R5. Realynx FruityLink SDK：项目身份、可获得性与许可

正确候选是 [Realynx/FL-Automation](https://github.com/Realynx/FL-Automation)，不是另一个同名 Midas M32 控制器项目。

本次查询 master：`c0a76bc5779728084a4165b08314a8575d5e781e`。

- [SDK capabilities](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/docs/capabilities.md)
- [Installation](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/docs/installation.md)
- [Development](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/docs/development.md)
- [MIT license](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/LICENSE)

实际提供 host/bridge/SDK 源码，但缺完整 installer/bootstrap 项目；构建 solution 不会自动安装 FL startup loader。当前文档 SDK0.2.0 套件及本地 installer0.1.26 未公开发布。GitHub releases API 本次返回公开 v0.1.8、2026-07-09、asset `fruitylink-installer-v0.1.8.zip`；旧包不证明当前全部能力。

外部 Python 客户端要求 Python3.11+；文档内置 private CPython3.14.6，不要求把系统 Python换成该版本。编译需要 .NET9 SDK、CMake、MSVC x64/MASM。不要混淆 SDK/host/bridge/Python/MCP 的版本号；更新核对内容哈希。

## R6. FruityLink 的实际契约与 Fl-MCP 的实测范围

- [INativeFlControl](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/src/FruityLink.Core/Abstractions/INativeFlControl.cs)
- [IFlStructuredQuery](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/src/FruityLink.Core/Abstractions/IFlStructuredQuery.cs)
- [API gaps](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/docs/api-gaps.md)
- [Automation clips](https://github.com/Realynx/FL-Automation/blob/c0a76bc5779728084a4165b08314a8575d5e781e/sdk/docs/automation-clips.md)
- [Fl-MCP live verification](https://github.com/Realynx/Fl-MCP/blob/b4526a41c5f67dd3f83f588f5194e58ec98d6839/docs/live-verification.md)
- [Fl-MCP building](https://github.com/Realynx/Fl-MCP/blob/b4526a41c5f67dd3f83f588f5194e58ec98d6839/docs/building.md)

Fl-MCP master 本次为 `b4526a41c5f67dd3f83f588f5194e58ec98d6839`，PolyForm Noncommercial1.0.0；它是独立适配器，不等于 SDK 的 MIT 许可。

接口和文档确实覆盖 AddChannel、batch note add/read/edit/delete、Pattern、Playlist、Automation首次link/points、plugin状态、项目快照。外部记录的 live build 是 **26.1.3.5570**；25.2.5.5319 只有 binary/fixture 范围；不能外推本机5639。

需带入设计的限制：query非原子；raw clip/note index不是持久ID；筛选空页仍可有 continuation；batch取消可留下完成前缀；Automation创建可部分成功且无自动rollback；某些plugin参数显示/实际送达会延迟；clone pattern不等于完整复制全部metadata；Sampler许多设置和channel delete/reorder仍是GUI路径。

live-verification 明确记录 saved FLP有5,341 notes、某次live enumeration为5,076，原因未解释；这正是新CLI需要保存快照交叉验证的理由。SDK export方法本身只打开对话框，Fl-MCP另有 owned process的render编排。背景模式是正常FL运行在private Windows desktop，不是去掉GUI引擎。上述均为上游记录，未在本机复验。

## R7. PyFLP

[demberto/PyFLP](https://github.com/demberto/PyFLP) master：`f937126b888ce94271bfea631b89166c74056530`，GPL-3.0。

- [pattern.py](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/pattern.py)：Note.rack_channel 指向 Channel.IID，不应与当前显示索引混为一谈。
- [arrangement.py](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/pyflp/arrangement.py)：版本相关 Playlist record、track反向索引、pattern/channel引用。
- [FAQ](https://github.com/demberto/PyFLP/blob/f937126b888ce94271bfea631b89166c74056530/docs/faq.rst)：无通用collection新增/删除API，主要修改已有对象；非线程安全。
- [PR207](https://github.com/demberto/PyFLP/pull/207)：Python3.12+ EventEnum查找修复，查询时open；head `2354fbf02bce463f2dcb5673d752cb3e4ac25c55`。
- [PR208](https://github.com/demberto/PyFLP/pull/208)：报告本机同版本FL26.1.6.5639 event172 3-byte导致解析对齐问题，查询时open。
- [Issue200](https://github.com/demberto/PyFLP/issues/200)、[PR205](https://github.com/demberto/PyFLP/pull/205)：新Playlist记录缺失/80-byte修复，open；PR自身仍注明某些编辑后的clip可变长，不能泛化固定长度。

这些 PR 是证据线索而非本机通过记录。本次没有安装PyFLP或将任何补丁应用到用户文件。首阶段必须用本机FL保存的 fixtures 验证读回与无修改往返，后续再考虑写入。

## R8. OpenCLI

本地 `E:\WorkSpace\tools\OpenCLI` HEAD：`916705f34456ea54200fb79d0a28fd1cbc0727f6`，Apache-2.0。

- [Architecture](https://github.com/jackwener/OpenCLI/blob/916705f34456ea54200fb79d0a28fd1cbc0727f6/docs/developer/architecture.md)
- [CDP backend](https://github.com/jackwener/OpenCLI/blob/916705f34456ea54200fb79d0a28fd1cbc0727f6/src/browser/cdp.ts)
- [Adapter pitfalls](https://github.com/jackwener/OpenCLI/blob/916705f34456ea54200fb79d0a28fd1cbc0727f6/skills/opencli-adapter-author/references/success-rate-pitfalls.md)

可借鉴 command registry、schema、doctor、session/target解析、结构化输出和观测证据。现有执行层主要是网络请求、Browser Bridge、CDP；FL原生窗口没有DOM/page target。Windows桌面外壳支持不等于Win32自动化能力。此次不安装Chrome扩展，不把OpenCLI当FL GUI后端。

## R9. 本机重新核实的基线

- FL64：`C:\Program Files\Image-Line\FL Studio 2026\FL64.exe`，Product/FileVersion `26.1.6.5639`。
- Engine：`C:\Program Files\Image-Line\FL Studio 2026\FLEngine_x64.dll`，FileVersion `26.1.6.5639`。
- Engine SHA-256：`BC3637C3E41694C820865E757D88A42BDC15B6DB4011582A2EF8F4D1B05A2D95`。
- 旧MCP venv解释器是 Python3.12.10；PATH的python却指向 `C:\Program Files\Python310\python.exe`。新项目必须显式选Python3.12并建立自己的venv。
- uv/git/node/dotnet 命令可解析；`dotnet --list-sdks`无输出，CMake未在PATH中找到。不能声称已具备FruityLink原生编译环境。
- 新项目目录此前不存在；未发现 E:\、E:\WorkSpace、tools或目标目录的文件型AGENTS.md。遵守会话给出的禁用hosted web_search规则。

规划建议来自以上当前只读核查。没有将任何外部live记录包装成本机结果，也没有创建运行脚本、改现有工程或结束FL进程。

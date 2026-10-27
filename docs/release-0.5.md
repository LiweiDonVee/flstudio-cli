# 0.5：Sytrus、Mixer 与完整 FX 链

本机 FL Producer 26.1.6.5639，2026-10-27。设计由 Astra XHigh 完成。
0.5.1 更正了 Sytrus 元数据：不同年代预设的前四字节不统一表示版本，现仅返回 `state_prefix_hex`，不解读私有格式。
0.5.2 收紧 Mixer 地址匹配：插件参数的低字节碰巧等于推子编号时，不会被误认成推子。
本轮沿用已有文件编辑器/原生渲染器，新增一个组合工作流回归，总计 4 个；未创建另一套测试框架。

## 交付

- 本机 generator/effect `.fst` 分类检索；Sytrus 保存宿主参数目录与整数编辑。
- build/edit 一份 JSON 完成 Channel→Insert→Bus→Master、推子、声像、静音和 send 电平。
- 完整效果链定义：加载、保状态复制/跨轨移动/交换顺序、移除、逐槽旁路与干湿、整链旁路。
- 保存参数 profile：Parametric EQ 2、Reeverb 2、Soft Clipper、Limiter 的明确宿主控制；保留 Emphasizer 专用验证器。
- `live --channel` 通过单独安装的控制器扩展使用全局索引；旧控制器未加载扩展时明确拒绝。
- MIDI 桥额外接收 RX 回路响应，修复 FL 自动分配 RX 为输出后失联，方向为请求的回声不会重复执行。
- 换新音源预设清理旧宿主覆盖；复制效果保留 start controls 优先级，避免新音色被旧静音/音高强制覆盖。

格式见 [sytrus-mixing.md](sytrus-mixing.md)，完整输入见 [examples/sytrus-mix.json](../examples/sytrus-mix.json)。

## 实际 FL 音频证据

| 工作流 | 实际结果 |
|---|---|
| Sytrus 明确目标 | 保存 IID 改成 7/13；目标 0 主音高 +12，基频估计约 260→524Hz；另一个声部主音量 0 后指定窗口 RMS=0 |
| 保存参数保持音色 | 只新增/更新宿主控制，两个 Sytrus 压缩状态 blob 保持原字节 |
| 发送电平 | Insert1→Bus6→Master；旋钮 1→0.5 后整体 RMS 0.02055995→0.00476289；非线性旋钮，不宣称半振幅 |
| 断链/侧链连接 | Bus 断开 Master 或 send=0 时实际导出全零音频；route 存在和音频电平分开保存 |
| EQ2 -6dB | `main_level=-600`，受控输入振幅比 0.501196 |
| 效果器参数寻址 | Reeverb2 的 dry/ER/wet 全0、Limiter gain=0、Soft Clipper post_gain=0，三个分别指定的时间窗 RMS 均为0 |
| 非线性效果顺序 | EQ2 与 Soft Clipper 交换，保存状态/宿主覆盖随实例迁移；增强探针差异 RMS=0.00676544 |
| 旁路与干湿 | 整链旁路，以及一槽 disabled 加另一槽 wet=0，输出分别与干声逐样本一致，差异 RMS=0 |
| 完整创作示例 | 两路 Sytrus、SYNTH BUS、EQ2→Soft Clipper→Reeverb2→Limiter，实际导出44.1kHz双声道16bit WAV，10.026秒，峰值0.11325；源文件不变 |

原始本机证据位于 `.lab/sytrus-mix/native-20261027-111020`，完整示例位于 `.lab/sytrus-mix/sytrus-mix-demo.flp/.wav`；这些本机产物不随包或仓库分发。

实际探针发现并修复：FL25/26 扩展 Mixer 的 send 地址低16位是 `0x2000+destination`，旧 `0x1f40+destination` 虽能在文件回读但不影响音频。
最初弱输入的换序差异低于预定阈值，随后增加同一 EQ 的驱动电平重新验证，没有修改通过阈值。
原回归和新增组合回归均通过，输入 FLP 与非目标音色状态保持不变。

## 覆盖边界

宿主参数目录不等于对每个旋钮做过独立声音认证。Sytrus 的 FM/RM 矩阵、谐波编辑与 envelope point 仍由完整音色或 GUI 处理。
带 automation/controller links 的工程目前拒绝整链重排；第三方插件任意自绘控件没有新增适配。
`plugin verify` 的专用受控输入仍针对 Emphasizer；其他保存参数使用真实前后工程音频验证。
实时音源扩展需要 FL 重载 MIDI 脚本，文件链不依赖这一步。
本轮属于上述工作流验证，没有重新声称新的 CLI/MCP 盲测结论；0.4 的独立比较仍仅对应当时三项任务。

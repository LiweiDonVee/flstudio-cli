# 0.3：按独立对比反馈改进

2026-10-26。Astra XHigh 对冻结0.2版本的中立评测结论为 **MCP略优**，因此没有创建或发布GitHub仓库。报告原件位于本机 `tools/fl-interface-evaluation/judgement-20261026-01/report.md`，旧结果保持原样。

本版改进：

- 修复现有FL26工程的Playlist记录：该版本原生记录为88字节，旧写法80字节会让FL忽略片段。相同五通道基线、原八音符输入已导出3.697120秒的有声WAV，源文件保留。
- 新增可选 `live` 命令，复用已连通的本地MIDI桥读取当前工程、改BPM、改Mixer声像、列出插件参数和按名称/索引改参数。使用标准库TCP客户端，不导入或启动MCP前端；桥和FL控制器仍是外部前提。
- live写入在命令内读回；插件数值和显示字符串可能不同步，数值尚未确认时返回unknown及提交前后值，不报强成功。`--dry-run`完全不连接桥。
- 新增保存文件的Emphasizer v2单参数配置：只改Emphasis，不替换整份预设或其他状态。原生音频发生变化，参数状态与FL实际保存的25%副本逐字节一致。

## 保存文件的命名参数

```powershell
flstudio plugin params --project song.flp --track 0 --slot 9
flstudio project edit --input song.flp --request one-param.json --output revised.flp
```

`one-param.json`：

```json
{"plugin_params":[{"track":0,"slot":9,"param":"Emphasis","value":0.25}]}
```

这个文件配置只覆盖已验证的Emphasizer状态v2、Emphasis参数。其他插件参数用 `live plugin-params` 发现并通过宿主API操作；没有把私有状态字节猜成通用插件接口。

## 本机验证

仍仅3个工作流回归。实际当前FL工程的BPM123/130、Mixer Insert1声像0.25/0已写入并回读；原值已恢复。插件Emphasis写入时的数值延迟已实测，CLI按unknown处理，原0.5013已恢复。

本轮原生导出和修改结果位于 `tools/fl-interface-evaluation/fix-verification-20261026/`，包括同输入修复音频、单参数修改音频和live请求/回读记录。0.2的MCP略优结论不自动升级为本版胜出；发布仍需独立评测满足用户规定的条件。

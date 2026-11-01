# 从参数成立到听感成立

## 证据阶段

| 阶段 | 必须留存的证据 | 结论范围 |
|---|---|---|
| 资料支持 | sources.json 的source_id、具体section/page/commit | 控制的机制有出处 |
| 状态实现 | 实际版本、init文件、字段/参数地址、修改前后值、未知字节保留 | 目标状态可构造/读回 |
| 插件闭环 | 真实插件加载、保存新副本、关闭/重开或独立新实例、再次读回 | 状态被该插件接受并持久化 |
| 音频机制 | 相同MIDI/tempo/render设置的前后WAV、静音/削波/音高/包络等检查 | 插件确实产生了与改动相符的信号差异 |
| 听感验收 | 有人实际试听的盲化/随机顺序比较、目标词和上下文反馈 | 该听众在记录条件下的选择 |

参数变化、成功返回码、谱重心变化、神经网络相似度和文件存在都不能跨过最后一步。
本页给出资料与评估协议；本机实际已完成的插件/音频闭环见[验证记录](../validation.md)。
听评未执行，单个配方的动作也不能因其他案例成功而自动标记为已验证。

## 演奏与渲染固定

保存一段单音长音、短音重复、实际音域内的低/中/高音、短和弦和固定伴奏片段。记录MIDI键号而不只记C4，因为宿主音名偏移可能不同。固定velocity、note长度、note-off、tempo、采样率、oversampling/HQ和render质量。3xOsc官方手册P03特别指出实时/渲染抗混叠行为及HQ开关，因此不要拿两种设置不同的输出归因于音色配方。

尾音窗口覆盖实际release与FX衰减；同时记录固定比较窗口，避免“文件更长”改变平均指标。随机相位或drift无法锁定时，记录它们并保留多次渲染，不能要求非确定性声音逐样本相等。

## dB与响度匹配

先保留raw WAV，再产生仅供对照试听的增益补偿版本。输出增益补偿优先放在合成/非线性处理之后，避免为了匹配响度改变drive或FM指数。

- 把peak dBFS、RMS dBFS、LUFS、dBTP分开标记；peak相同不意味着同样响。
- 对足够长、相同内容与窗口的片段，可用符合BS.1770的响度计测得`LA`和`LB`，对B施加 `gain_db = LA - LB`；线性振幅乘 `10 ** (gain_db / 20)`。不要把dB差直接乘在样本上。
- 若只有短音符、稀疏瞬态或静音尾音，门限/窗口会明显影响LUFS。可把固定短音序列重复为较长片段，另报活跃段RMS/peak，并由人微调对照响度；没有一种数值可保证主观等响。
- 检查补偿后的peak/true-peak余量；若某一条超限，对两条施加相同的额外衰减，保持相对匹配。不要对其中一条单独加limiter后继续当纯音色比较。
- 本库可选的初始匹配容差为0.5 LU，是内部操作选择，不是“听不出差别”的研究阈值。EBU R128的−23 LUFS属于广播programme交付目标；不把它强制用作单个合成音色的制作电平。

E01支持“loudness”和“peak限制”必须分开，及programme测量需要明确窗口/门限。E01同时不建议对短于1分钟的programme使用LRA；因此不要给2秒音符报告一个具有审美意义的LRA排名。

## 试听与上下文

保留原始参考音与目标描述。把候选名隐藏成A/B，交替顺序，允许“不确定/都不符合”，先比较干音再比较固定伴奏。逐项询问或记录“更柔和/更亮/更有气息/更厚/更清楚/颗粒是哪一种”，不要只问“哪个更好”。本地Agent没有听音能力时，`listening_status`必须为`not_performed`，不填写编造评分。

检查单声道 `M=(L+R)/2`，并保留立体声版。记录低音、旋律清晰度、尾音堆积、和弦粗糙度、音高稳定与混音遮蔽。频谱、包络、相关系数、mid/side电平用于发现机制或故障，不是听感词的真值。

## 最小记录模板

```json
{
  "intent": {"word": "温暖", "interpretation": "高次谐波较少且仍清楚", "reference": null},
  "plugin": {"name": "Sytrus", "version": "record-from-installed-plugin"},
  "baseline": {"path": "absolute-init-path"},
  "sources": ["P01", "P02", "C02"],
  "changes": [{"control": "FILT1.CUT", "display_before": "record", "display_after": "record", "unit": "plugin-display"}],
  "state_readback": "not_performed",
  "native_render": "not_performed",
  "level_match": {"window": null, "method": null, "gain_db": null},
  "listening_status": "not_performed",
  "decision": null,
  "fallback": "减少cutoff改变量，或改用triangle起点"
}
```

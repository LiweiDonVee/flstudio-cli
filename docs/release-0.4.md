# 0.4：原生参数响应验证

针对Astra独立反馈中的参数宿主确认缺口，新增 `plugin verify`：保存只改一个参数的新工程，同时用实际FL引擎渲染同一效果器状态的前后对照。诊断副本使用受控的多频输入；源工程与当前编辑器不动。

```powershell
flstudio plugin verify --project song.flp --track 0 --slot 9 --param Emphasis --value .25 --output-dir checked
```

输出 `checked/project.flp`、独立的前后诊断工程/WAV及 `verification.json`。目前只覆盖已核对的Emphasizer v2 Emphasis参数，其他参数不猜测私有状态。

此前八个安静Kick的前后音频相同，不能单独判定参数未生效。受控多频输入下，0.5013→0.25的真实音频差值RMS约0.109、最大样本差约0.672，远大于16位量化/抖动。产品命令已实际复现该响应，并核对源文件未变。

返回verified的范围是保存参数状态、FL原生导出和受控输入下的参数音频响应。不会把它冒充当前GUI参数读回；诊断没有取得响应时返回unknown。dry-run不创建输出目录或启动FL。

仍保持3个工作流回归，未新增测试模块。后续独立评测记录另存，0.3的旧结论保持原样。

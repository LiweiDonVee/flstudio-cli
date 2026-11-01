# Surge XT 对照：init、filter 与 envelope

## 版本与实现边界

本机只读执行 `E:/WorkSpace/tools/flstudio-cli/.lab/fullstack/plugins/surge/surge-xt-cli.exe --version`，返回 **`1.4.nightly.dab78c6`**。官方在线手册 P04 明确面向 **1.3**。源码 P05 锁定到同 hash 的完整 commit `dab78c6170732b3883216e569a84bf084ae0ea97`（2026-10-25）。手册控制名称可以指导操作，但菜单、参数枚举和状态仍要由实际版本读回。

`surge-xt-cli --help` 确认支持 `--init-patch <path>`、OSC 输入/输出端口、sample-rate/buffer-size 与 MIDI 输入；CLI 本身不是“离线导出WAV并断言听感”的证据。此次只执行 help/version，未启动音频实例。

## init 不能只看名字

P05 `SurgePatch::init_default_values()` 会重置大部分参数，但有 master volume、fx_bypass 等例外；`polylimit` 另设默认值。源码可见 O2/O3、noise、两组ring的mute为true；scene width=1，keytrack root=60，oscillator keytrack=true。AEG/FEG的A设到参数最小值，D=-2、R=-5、S=1；这些是内部参数值，**不是秒数或宿主归一化值**。

因此受控 baseline 应显式指定场景、活动振荡器、FM/RM、filter类型/route/config/balance、AEG/FEG、FX bypass、宏与调制，保存完整patch，再独立读回。调用某个名为init的函数并不足以证明两次声音相同。随机相位、osc drift和未覆盖的全局音量也要记录。

## filter 与 envelope 的最短有效路径

1. 使用一个可发声的富谐波oscillator（例如Classic saw），先mute其它osc/noise/rings，关闭附加效果。先证明干音有声。
2. Filter1选择低通，保持低resonance；检查filter configuration与balance确实把信号送进F1。不同串/并联结构和waveshaper位置会改变结果，不能仅凭cutoff值比较。
3. 手动扫 F1 cutoff，利用tooltip记录 **Hz和近似MIDI音名**。先证明滤波路由有效，再添加调制。
4. 修改 **FEG Mod Amount `>F1`** 才让Filter EG的曲线影响F1；`>F2`独立控制F2。仅编辑FEG ADSR而深度为0，不会产生预期的滤波动态。
5. AEG控制幅度形状，FEG控制滤波动态。二者均是ADSR；S是保持电平，R在note-off后执行。选择Analog/Digital曲线模式并记录；同一组时间值不保证相同轮廓。
6. 比较前后参数与原生音频；调整输出增益匹配后，再判断亮度、拨感或柔和程度。

## 必须单独记录的开关

| 控制 | 已读到的机制 | 排错意义 |
|---|---|---|
| F2 Offset Mode（小`+`） | F2 cutoff相对F1偏移，跟随F1 cutoff及其modulation、FEG depth、keytrack（P04） | 改F1时F2也变化不一定是写串参数 |
| Filter Keytrack | 100%时cutoff跟随音高；Keytrack Root决定参考点（P04） | 固定cutoff和谐波跟随是不同实验；必须固定演奏音域 |
| Filter configuration / balance | 两filter如何串并联/混合；waveshaper在不同配置的位置不同（P04） | 没声音/效果小先查路由，不继续加FEG深度 |
| Analog/Digital与curve | 改变包络段的形状（P04） | 用实际包络/音频验证，不只比较A/D/R显示数字 |
| Tempo sync | 可逐段或同时同步EG参数（P04） | 记录tempo-sync标志；不能把拍长和秒混用 |

## 已核对源码的语义地址

P05 `SurgePatch.cpp` 包含以下OSC参数语义名。它们帮助发现参数，不构成已运行OSC接口的认证：

- `/param/a/osc/1/type`：Scene A、Osc1类型；具体枚举需本机读取。
- `/param/a/filter/1/type`、`/param/a/filter/1/cutoff`、`/param/a/filter/1/resonance`。
- `/param/a/filter/1/feg_amount`、`/param/a/filter/1/keytrack`。
- `/param/a/filter/2/offset_mode`、`/param/a/filter/config`、`/param/a/filter/balance`。

`OpenSoundControl.cpp` 通过实际参数对象解析地址，区分参数查询与写入。执行时应先枚举/查询支持的地址及显示值，再写入并回读；Hz、秒、枚举索引与`0..1`值的转换须由该版本参数类型完成。不要把参数名拼接或源码内部浮点值当作可直接发送的物理单位。

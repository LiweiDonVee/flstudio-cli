# 0.4.1：CLI 自有 MIDI 桥与 DSH 迁移

新增 `bridge start/status/serve/stop`，由CLI直接持有MIDI输入/输出，通过控制器兼容SysEx协议访问FL。默认只监听127.0.0.1:9787；不导入旧MCP模块，也不启动MCP server或daemon。

```powershell
uv tool install --editable ".[midi]" --python 3.12
flstudio bridge start
flstudio live status
```

核心文件功能仍只依赖Click/Pydantic。MIDI为可选依赖mido/python-rtmidi；新机器仍需配置虚拟端口和FL控制器。
Windows无控制台登录启动已验证，`bridge start`可以按需启动已安装的loopMIDI。停止命令会先核对CLI桥身份。
升级已运行的CLI MIDI服务时，先`bridge stop`，升级后再`bridge start`，避免Windows锁定运行中的入口程序。
`live query/apply`接管控制器已有的播放/停止、定位、音量、静音、路由等原语；apply强制指定独立回读及预期值，不以setter回包代替确认。请求示例见[live-commands.md](live-commands.md)。

本机DSH的FL Studio预设已迁至PowerShell调用CLI：移除FL MCP客户端/工具schema，替换旧写谱和人工导入/导出说明；保留同一preset ID、文件工具和上下文压缩。
旧MCP server/daemon及旧登录入口已关闭，CLI桥实际取得心跳，读回130BPM、5通道、18混音轨及Emphasizer参数。

仍保持3个工作流回归；没有新增测试模块。此补丁替换连接进程的实现，原有FLP编辑、参数验证和原生音频功能不变。

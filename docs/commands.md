# 命令入口

当前版本1.0.3。业务输出为UTF-8 JSON；帮助也由 `--help` 返回。无需旧MCP或9787服务。

| 命令 | 实际作用 |
| --- | --- |
| `doctor` | 查看安装文件版本、hash和运行环境 |
| `project build --request JSON --output FLP` | 创建采样器/本机预设音源、多Pattern音符与Playlist工程 |
| `project inspect --input FLP [--summary]` | 读回通道、音符、Playlist、Mixer及插件状态hash |
| `project edit --input FLP --request JSON --output FLP` | 组合音符、样本、通道、路由、Mixer、效果器变更 |
| `notes list --project FLP --pattern-number N [--channel-index N]` | 读取明确目标的音符 |
| `notes replace --project FLP --pattern-number N --channel-index N --notes JSON --output FLP` | 保存新副本，其他通道的音符记录不变 |
| `plan build --request JSON --plan-out JSON` | 为带output路径的notes.replace请求建立源hash绑定计划 |
| `plan apply --file JSON` | 检查请求hash和源hash后写入新副本 |
| `render wav --project FLP --output WAV` | 实际FL原生渲染，当前编辑器可保持打开 |
| `audio inspect --input WAV` | 查看实际PCM帧数、时长、峰值/RMS、dBFS、每声道电平与crest factor |
| `capabilities` | 已实现与尚未实现的能力分开列出 |
| `flp probe --input FLP` | 仅检查容器，比完整inspect更有限 |

请求示例和单位见 [quickstart-0.2.md](quickstart-0.2.md)。

build/edit/notes replace/render wav/plan apply都支持 `--dry-run`。
未显式要求的文件不会写入。请求错误退出2，文件/渲染失败退出5，旧的不完整apply请求退出7。
`project build/edit` 和 `notes replace` 成功是保存文件的产物级验收；
不能将它理解为已打开编辑器内存中的状态被修改。

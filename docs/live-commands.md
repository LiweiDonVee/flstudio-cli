# 实时宿主原语

常用操作可直接用 `live set-tempo`、`live set-mixer-pan`、`live plugin-params`、`live set-plugin-param`。
其他已装控制器支持的操作使用 `live apply --request change.json`，强制给出独立回读条件。旧MCP前端不参与执行。

停止播放的请求：

```json
{"command":"stop","params":{},"readback":{"command":"get_play_state","params":{},"expect":{"playing":false}}}
```

播放改为`command:"play"`、`expect:{"playing":true}`。录音使用控制器的`record`命令并核对`recording`；仅在用户明确要求录音时执行。

其他原语及参数示例：

| 写命令 | params示例 | 回读命令及params | expect示例 |
| --- | --- | --- | --- |
| set_song_position | `{"beats":0}` | get_song_position `{}` | `{"beats":0}` |
| mixer_set_volume | `{"track":1,"value":0.8}` | mixer_get_track `{"index":1}` | `{"vol_norm":0.8}` |
| mixer_set_mute | `{"track":1,"state":true}` | mixer_get_track `{"index":1}` | `{"mute":true}` |
| mixer_set_solo | `{"track":1,"state":true}` | mixer_get_track `{"index":1}` | `{"solo":true}` |
| mixer_set_name | `{"track":1,"name":"DRUM BUS"}` | mixer_get_track `{"index":1}` | `{"name":"DRUM BUS"}` |
| channel_set_volume | `{"channel":0,"value":0.8}` | channel_get `{"index":0}` | `{"vol_norm":0.8}` |
| channel_set_pan | `{"channel":0,"value":0.25}` | channel_get `{"index":0}` | `{"pan":0.25}` |
| channel_set_mute | `{"channel":0,"state":true}` | channel_get `{"index":0}` | `{"mute":true}` |

读对象：`live query --command COMMAND --params-file params.json`。
可选命令由 `live query --help` 列出，覆盖播放/定位、Mixer/通道、插件、Pattern和路由查询。
参数JSON中Mixer读取是`index`，Mixer写入是`track`；通道写入使用`channel`。

桥只转发已安装控制器实现的命令；未知命令会报错，不提供任意Python执行。
apply写前先保存回读值，写入一次后轮询条件；不因setter回包就宣称完成。unknown不应连续重发。
`--dry-run`只校验请求，不连接桥。live修改不保存当前工程。

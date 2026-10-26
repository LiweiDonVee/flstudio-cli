结论：**CLI明显更优**，限于本轮三个等权目标及已配置环境，不代表覆盖全部FL GUI工作流。标准先记于 criteria.md；依据为实际读回、保存文件和独立PCM解析。

状态目标两者接近：均发现五通道工程，123 BPM、Insert1声像+0.25都读回成功。最终恢复130、0及Emphasis 0.5013（50%），其余参数一致，源文件未变。

参数目标CLI有实证优势：两边实时写0.25后均显示25%，数值却仍0.5013，精确生效未确认；CLI返回unknown，MCP返回ok但附带矛盾读值。CLI保存副本读到0.25，独立字节检查仅目标状态变化。复制完整效果的两个诊断工程仅该状态不同，经真实FL渲染，PCM差值RMS为0.10896。这证明保存状态被引擎消费，不证明当前GUI已改。

创作目标CLI完成：保留五通道及效果，八音符、PPQ96、130BPM和Track1的0..768tick片段均回读吻合；真实FL导出44.1kHz/16bit立体声WAV，独立解析3.697秒、RMS 0.10309。MCP导出MIDI的八音符正确；导入原通道、放片段、另存和渲染尚未执行。公共CUA截图超时后停止，不将人工步骤未完成计作失败。

建议本组保存编曲与交付用CLI；MCP可用于现有会话状态发现、基础控制和MIDI协作。两条live路径均依赖已配置MIDI桥及控制器；渲染需本机FL和素材。新机部署、其他插件、任意GUI操作及人工接续结果未测；CLI单独安装不等于具备live能力。

证据：live-results.json、final-live-state.json、independent-evidence.json、cli-plugin-verify-result.json、cli-arrangement-render-result.json、mcp-arrangement-results.json、gui-observation.json。

# 配置公开化说明

这个目录同时包含了树莓派回收下来的原始配置文件和适合公开仓库使用的模板文件。

## 建议公开保留

- `voice_agent.env.example`
- `edge_bridge.env.example`
- `sensor_hub.env.example`
- `mjpeg_stream.env.example`
- `class_map.json`

## 不建议直接公开提交

- `voice_agent.env`
- `edge_bridge.env`
- `sensor_hub.env`
- `mjpeg_stream.env`
- `mjpeg_stream.env.codex.bak2`

原因：

- 这些文件可能包含真实设备编号、后端地址、服务端口、语音模型路径、缓存路径和 API key
- 真实运行配置通常只适合部署机本地保留

## 推荐用法

1. 将 `*.env.example` 复制为对应的 `*.env`
2. 按部署环境修改路径、后端地址和模型位置
3. 将真实密钥填入本地配置，不要提交回仓库

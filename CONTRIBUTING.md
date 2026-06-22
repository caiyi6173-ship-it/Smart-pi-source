# 贡献指南

感谢你关注 `smartpi`。

这个仓库同时包含树莓派设备侧代码、RAG 服务、OpenClaw 集成和视觉实验代码。为了让协作更顺畅，建议在提交前先看完这份说明。

## 1. 提交前先了解项目结构

建议先阅读：

- [README.md](README.md)
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- [DEPLOY_RASPBERRY_PI.md](DEPLOY_RASPBERRY_PI.md)

## 2. 分支与提交建议

- 小改动尽量聚焦一个目标
- 不要把无关重构和功能修改混在一个提交里
- 提交说明尽量写清这次改了什么

推荐的提交说明风格：

```text
fix: correct smartpi service name in deployment script
docs: add Raspberry Pi deployment guide
feat: improve rag hybrid retrieval routing
```

## 3. 配置与敏感信息

不要提交以下内容：

- 真实 `.env`
- API Key
- 模型权重
- 运行日志
- 缓存目录
- 采集图片、音频、视频
- 数据库状态文件

请优先使用：

- `config/*.example`
- `rag-chroma/.env.example`

## 4. 代码风格

### Python

- 优先保持现有模块结构
- 小步修改，避免一次混入大量无关重构
- 新增逻辑时，尽量保持命名一致和职责清晰

### Shell

- 使用明确路径
- 保持脚本可重复执行
- 修改部署脚本时，注意同步 service 文件和文档

### 文档

- 顶层文档以中文为主
- 如果新增英文说明，请与中文内容保持一致

## 5. 测试建议

如果你修改了以下内容，请尽量补对应验证：

- `rag-chroma/`：至少验证导入、检索、查询链路
- `edge/`：至少检查关键脚本参数、service 名称、路径引用
- `openclaw/`：至少检查 skill 名称、动作标记和调用入口

建议在提交前完成：

- Python 语法检查
- Shell 语法检查
- 关键入口 `--help` 冒烟检查

## 6. 部署相关修改

如果改动涉及树莓派部署，请同时检查：

- `/home/pi/smartpi/...` 路径是否一致
- `config/*.example` 是否需要同步
- `edge/*.service` 是否需要同步
- `README.md` 或 [DEPLOY_RASPBERRY_PI.md](DEPLOY_RASPBERRY_PI.md) 是否需要更新

## 7. Issue / PR 建议

提 Issue 或 PR 时，建议说明：

- 修改目标
- 影响模块
- 是否涉及树莓派实机
- 是否涉及模型、传感器、摄像头、OpenClaw、RAG
- 如何验证

## 8. 当前最需要的贡献方向

- 树莓派端部署流程标准化
- RAG 自动化测试补齐
- YOLO 目录收敛与整理
- OpenClaw 集成文档完善
- 硬件接线与传感器说明补齐

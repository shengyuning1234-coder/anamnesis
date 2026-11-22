# 忆溯 / Anamnesis

忆溯是英语词汇学习工具，支持词典查询、材料录入、单词本、复习与测验，也可配置 AI 辅助释义和情境出题。Docker 部署集成 OpenWebUI 对话和个人词库 MCP。

## 本地启动

- macOS 安装 Python 3.11 或更新版本后，双击 `启动忆溯.command`。
- Windows 安装 Python 3.11 或更新版本后，双击 `start-local.bat`。

浏览器访问 http://127.0.0.1:5050，首次使用时设置管理员密码。学习数据和本机配置默认存放在 `英语单词/data/`。

需要离线释义和更完整的干扰选项时，可运行以下命令下载指定版本的资源并生成词库索引。Windows 用 `py -3` 代替 `python3`。

```sh
python3 英语单词/prepare-lexicons.py
```

如果有可用的 MDX 词典，可将其命名为 `oaldpe.mdx` 并放进 `朗文英汉/`。本地词典资源与生成的索引保存在使用者电脑上。

## Docker 部署

将 `.env.example` 复制为 `.env`，按实际入口和数据目录编辑，然后运行 `sh 部署生产.sh`。默认入口为 http://localhost:5050/words/。需要把离线词库与 MDX 一并打包到镜像时，先按上文准备资源。部署要求和升级步骤见 [Docker 部署说明](DOCKER部署说明.md)。

Windows 可用 `start-local.cmd` 启动本机 Docker 环境。macOS 的 `启动内置对话.command` 使用已有的 `anamnesis:2026.10.25` 本机镜像，适用于此前配置过的本地对话环境。

## 项目文件

- `英语单词/` 包含 Python 服务、前端和测试。
- `docker/` 包含部署、网关、健康检查和集成工具。
- [AI 出题说明](AI出题说明.md)、[需求核对](需求核对.md)和[验收记录](验收记录-20261031.md)记录了功能和验证范围。

# 忆溯 / Anamnesis

忆溯是一款可自行部署的英语词汇学习工具。阅读时查词，把想记住的词收进单词本，再用间隔复习和测验巩固。

## 功能

- **查词与录入**：查询词义，或从阅读材料中提取单词，按主题存入单词本。
- **复习与测验**：按 FSRS 安排复习，支持本地选择题和回忆题。
- **AI 辅助**：配置模型后，可按需补充例句和用法，或生成情境题。
- **集成对话**：Docker 版集成 OpenWebUI，可在对话中通过 MCP 使用个人词库。

## 快速开始

```sh
git clone https://github.com/shengyuning1234-coder/anamnesis.git
cd anamnesis
```

安装 Python 3.11 或更新版本。macOS 双击 `启动忆溯.command`，Windows 双击 `start-local.bat`。打开 http://127.0.0.1:5050，首次访问时设置管理员密码。学习数据默认存放在 `英语单词/data/`。

如需离线词义和更完整的测验选项，可运行以下命令生成词库索引。Windows 用 `py -3` 代替 `python3`。

```sh
python3 英语单词/prepare-lexicons.py
```

如果已有可用的 MDX 词典，可将文件命名为 `oaldpe.mdx`，放到 `朗文英汉/`。

## Docker 部署

需要 Docker 和 Docker Compose。Linux AMD64 从仓库根目录执行以下命令。如需将离线词库和 MDX 词典打包到镜像，先按上文准备资源。

```sh
cp .env.example .env
# 按实际访问地址和数据目录编辑 .env
sh 部署生产.sh
```

默认入口为 http://localhost:5050/words/。Windows 可用 `start-local.cmd` 启动 Docker 测试环境。[Docker 部署说明](DOCKER部署说明.md)

## 更多文档

- [AI 出题说明](AI出题说明.md)
- [需求核对](需求核对.md)
- [部署验收记录](验收记录-20261031.md)

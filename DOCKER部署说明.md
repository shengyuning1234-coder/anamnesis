# Docker 部署（2026-11-01）

当前为单容器、单公开端口，源码构建目标为 `anamnesis:2026.10.31-full`，固定 linux/amd64。本次先交付源码，尚未完成该完整版镜像构建与运行验收。具体已通过项和限制见《验收记录-20261031.md》。单词应用在 `/words/`，对话同域嵌入；5051、5052 仅供内部使用。

编辑 `.env`：`APP_PUBLIC_URL` 填浏览器实际访问的完整入口，如 `http://192.168.1.100:5050` 或 HTTPS 域名，不带子路径。`APP_PORT` 是宿主机入口端口。数据路径可使用默认相对路径，也可指定 NAS 绝对路径。


## 本机测试

Windows 双击 `start-local.cmd`，或运行 `docker compose -f compose.local.yaml up -d --build`。入口为 `http://127.0.0.1:5050/words/`，容器名 `anamnesis-local`。单词和对话数据分别保存在 `./.local-preview/anamnesis` 和 `./.local-preview/openwebui`。

此入口自动提供集成 OpenWebUI，登录单词平台后即可进入「对话」，无需填写另一个 OpenWebUI 地址。页面折叠开关在右下角「页面布局」菜单。

## 从源码构建

```sh
cp .env.example .env
sh 部署生产.sh
```

需要访问 GHCR 和 PyPI；OpenWebUI v0.12.3 完整版基础镜像固定 digest（非 slim）。如需离线词库，请先执行 `python3 英语单词/prepare-lexicons.py` 生成索引，并按根目录 README 准备可选 MDX 词典。构建会将已有词库和 MDX 打包进镜像。

## 数据与升级

Compose 分别挂载 `WORDS_DATA_DIR` 到 `/data/words`，`WEBUI_DATA_DIR` 到 `/data/openwebui`。NAS 图形界面也可只挂载一个包含 words、openwebui 子目录的总文件夹到 `/data`；二选一，不要重复覆盖。镜像不包含个人数据、密码或 API Key。

更新前停止旧容器并备份整个数据目录（含隐藏文件），新容器沿用原映射。旧版 `/app/data` 的内容需放入新总目录的 words 子目录；不要让新旧进程同时读写。首次识别旧库会备份并迁移。JSON 导出不能替代完整数据目录备份。

## 访问与 AI

入口根地址自动转到 `/words/`。首次设定密码；必要时临时使用 `ALLOW_INITIAL_SETUP=1`，设定后改为 0 并重建容器。旧版账号自动成为 `admin` 管理员，原密码继续使用。新用户可由管理员创建，或开启注册后自行注册。

一体化 OpenWebUI 通过平台账号自动建立对应身份，模型配置仍由 OpenWebUI 自己管理。若要沿用旧版 OpenWebUI 管理员和聊天记录，先在「账号 → 用户管理 → 编辑 admin」绑定其原邮箱。容器启动时自动注册原生 MCP 服务器并设置模型默认工具，新对话默认启用；工具自动按当前用户身份访问个人词库，无需安装、填写服务地址或 Token。独立部署的工具使用个人 Token，不能共用管理员 Token。

单词项目在「设置 → AI 服务」配置兼容接口、Key 和模型，或在「账号 → 多模型与场景」分配模型。图片识别需选择支持视觉的模型；AI 出题在学习页主动选择。单词平台的 AI 额度不包含 OpenWebUI 自身的模型用量。

反向代理只转发一个入口到 5050，保留所有路径、Host、X-Forwarded-Proto，开启 WebSocket 并关闭流式响应缓冲。无需第二个对话域名或公开 5051/5052。

MCP 外部地址为 `入口/words/mcp`，Token 见设置；工具及流程提示词见 `英语单词/deploy/`。容器内工具调用地址为 `http://127.0.0.1:5052/mcp`。

新增账号、设备登录记录保存在单词数据目录的 `accounts.db`，各用户数据保存在 `users/用户ID/`；旧管理员继续使用根目录数据。请备份整个数据目录，不能仅备份旧 `words.db`。

本轮已验证本地真实 OpenWebUI 的账号自动登录、内嵌页面、WebSocket 身份认证、原生 MCP SDK 初始化/发现/个人词库调用、真实联网搜索及 OpenWebUI 搜索返回来源；未验证生产数据和真实模型推理。测试覆盖、已实现内容和待验收项见《验收记录-20261031.md》；旧《需求核对.md》保留为历史记录。

## 随镜像交付的 MCP 与本地网络搜索

镜像内新增 `docker/local_services.py`，只监听容器回环地址 5053，不开放宿主机新端口。`/mcp` 是 OpenWebUI 原生 Streamable HTTP MCP 入口，自动发现个人词库与网络搜索共 12 个工具；OpenWebUI 连接使用当前用户会话认证，服务端验证后交换该用户的个人词库凭据，禁止共用管理员 Token。外部客户端继续使用原来的 `/words/mcp` 和个人 Token。

`/search` 在本地进程检索公共搜索引擎，优先读取 Bing 的公开 RSS，失败时通过镜像内 DDGS 9.16.1 尝试其他公共搜索引擎。无需注册第三方搜索 API、付费搜索 Key 或宿主机安装程序。搜索依然需要容器可连接互联网，公共搜索引擎可能限流；失败会返回错误，不生成伪造结果。结果包含标题、摘要和原始来源链接，缓存 5 分钟并限制并发。

`docker/bootstrap.py` 每次启动都会等单词服务和 OpenWebUI 就绪，再通过 OpenWebUI 管理 API 自动注册 MCP、配置本地搜索、合并默认模型元数据，并更新已有工作区模型的工具默认项。保留模型供应商、API Key、其他工具、聊天记录和用户数据。启动器为内部搜索生成随机认证值，不需要用户提供；每次启动自动更新该值。OpenWebUI 引擎类型使用其 `external` 适配器，地址固定为同容器 `http://127.0.0.1:5053/search`，没有依赖外部托管搜索服务。

已开启跳过搜索嵌入与网页加载器：搜索摘要和来源直接进入对话上下文，不需要嵌入模型、相关 API Key 或额外模型下载。新对话默认启用词库 MCP 和网络搜索；已有对话可能保存了之前的工具选择，可新建对话测试。模型推理仍使用你在 OpenWebUI 中配置的模型。

镜像构建、安装依赖、服务启动、自动配置与健康检查均由项目内 Docker 文件完成。按原有数据映射运行 `sh 部署生产.sh` 即可升级，不需要另外在本机配置搜索。健康检查只有在三个业务服务与自动接入均就绪后才通过；启动失败会记录 `[Integration]` 日志并重试。

可在运行中的容器验证真实接通：

```sh
docker exec anamnesis-local python /opt/anamnesis-docker/verify_integrations.py
```

该验证自动创建并清理临时登录，测试原生 MCP SDK、个人词库、真实联网搜索和 OpenWebUI 搜索返回来源，不需要用户密码。

实现依据：OpenWebUI v0.12.3 的 `routers/configs.py`、`utils/tools.py`、`retrieval/web/external.py`；免密钥检索库见 https://pypi.org/project/ddgs/ 。

已另用全新临时数据容器验证首次启动自动配置，以及两个普通账号通过原生 MCP 建组、列出分组和数据隔离。临时测试容器不挂载用户目录，也不开放宿主机端口。

## 本地 embedding 与原生记忆

已增加 384 维多语言 MiniLM ONNX CPU 服务（容器内 5054）、Chroma 1.5.9 持久化向量存储（`/data/openwebui/vector_db`）。模型权重固定 revision，在镜像构建时下载并验证，运行时无需联网下载、外部 embedding 服务或用户 Key。当前使用完整版原生 Chroma，已移除精简镜像向量限制补丁，保留原版本和向量格式。

启动时用 embedding 更新 API 刷新 OpenWebUI 内存中的向量调用配置；模型版本变化时从 SQL 正文重建原生记忆索引。已有知识库若来自其他 embedding 模型，应重新索引对应知识库。备份需覆盖整个 OpenWebUI 数据目录，包括向量库。

原生记忆按用户账号共享，尚未按助手隔离；跨对话召回、后台自动提炼默认开启，每完成一轮回复检查一次。提炼使用当前聊天模型，可能消耗其额度，embedding 与存储在本容器内完成；不批量回填历史聊天。完整隔离设计、当前能力与使用限制见《OpenWebUI记忆方案.md》。可在容器内运行 `python /opt/anamnesis-docker/verify_memory.py` 验证中英文向量与原生记忆语义召回；此验证不调用聊天模型。

## 完整版镜像与升级衔接

基础镜像固定为 `ghcr.io/open-webui/open-webui:v0.12.3@sha256:a537bbe1e6b428820f52ed4a029d7fff97062e24d5cf32c365fba36fd0542def`。从同版本 slim 切换，无须新建账号或重新配置模型连接；继续挂载原来的 words/openwebui 数据目录，保留 `.webui_secret_key` 和 `.session-secret` 等隐藏文件。旧镜像 `anamnesis:2026.10.28` 可保留用于回退，升级前停止容器并完整备份数据。

项目额外安装 Chromium 及其系统依赖、LibreOffice 文档组件、Poppler、Tesseract 中英文识别和中日韩字体。Compose 为浏览器提供 1 GB 共享内存。无需在宿主机安装这些工具。完整版原有 Torch CPU、Transformers、文档加载器、语音、检索重排和各类存储适配路径恢复；第三方服务的接口仍需要对应服务与凭据。

基础镜像预装的 Whisper、辅助模型及 tokenizer 缓存转存到不可变的 `/opt/anamnesis-bundled-cache`，启动时仅补齐持久化 `/data/openwebui/cache` 中缺少的文件，不覆盖已有模型文件；Whisper、Hugging Face 和 tokenizer 路径均指向持久化目录。运行默认允许按需下载附加模型，避免旧精简版离线限制导致新功能无法加载。既有多语言 ONNX embedding 和 Chroma 配置继续沿用，记忆无需重建。

登录流程仍是：登录单词平台后，以可信内部身份进入 OpenWebUI，无需第二次输入密码；不开放匿名访问。注册策略、用户资料、模型供应商、Key、聊天、知识库及记忆沿用旧数据。自动记忆保持每轮后台提炼与跨对话召回，同账号的助手仍共享记忆。

完整版指上游完整依赖与功能路径，并非预装所有聊天、重排、语音合成、图像生成模型，也不包含云服务账号。聊天继续使用既有模型连接；重排、图像、语音合成等按各自功能需要选择模型或服务，不覆盖原有选择。Docker Desktop 的标准镜像使用 CPU，GPU/CUDA 需要另选对应基础镜像并配置 GPU 透传。

完整版适配自检：

```sh
docker exec anamnesis-local python /opt/anamnesis-docker/verify_full_image.py
docker exec anamnesis-local python /opt/anamnesis-docker/verify_memory.py --background
docker exec anamnesis-local python /opt/anamnesis-docker/verify_integrations.py
```

第一项实际启动 Chromium、通过原生加载器读取 DOCX/XLSX/PDF、执行 Office 转换，并从本地缓存加载 Whisper 做 CPU 音频推理。第二项以模拟的聊天模型提炼结果验证原生后台调度、真实 API 写入以及新对话的记忆注入，不调用付费聊天模型；不代表模型在实际对话中的提炼质量评测。临时记忆与登录会自动清理。

## 自动下载与首次启动

构建时自动安装系统及 Python 依赖。BUNDLE_EMBEDDING_MODEL=1 默认下载固定版本本地向量模型；AUTO_DOWNLOAD_MODELS=1 在启动时补齐缺失模型，PREFETCH_WHISPER=1 预加载语音模型。模型保存在持久数据目录。首次下载耗时较长，脚本等待健康最多 1200 秒；网络慢时可查看 docker compose logs -f 后继续等待。不要删除已有数据目录。

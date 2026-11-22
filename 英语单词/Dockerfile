# ============================================
# 英语单词背诵记忆系统 — Docker 镜像
# 适用于绿联云 NAS (Linux + Docker)
# ============================================

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（SQLite 等）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装 Python 包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码
COPY . .

# 创建数据目录（运行时挂载卷会覆盖）
RUN mkdir -p /app/data /app/dict

# 暴露端口
EXPOSE 5050

# 环境变量（可在 docker-compose 中覆盖）
ENV PORT=5050 HOST=0.0.0.0 APP_DATA_DIR=/app/data
ENV LOCAL_DICT_PATH=/app/dict/oaldpe.mdx

# 启动命令
CMD ["python", "web_server.py"]

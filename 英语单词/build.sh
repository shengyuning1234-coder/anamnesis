#!/bin/bash
# ============================================
# 英语单词背诵记忆系统 — 镜像构建与导出 (Linux/NAS)
# 用法: bash build.sh
# ============================================

set -e

echo "============================================"
echo "  英语单词背诵记忆系统 — 镜像构建与导出"
echo "============================================"
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "[错误] 未检测到 Docker"
    exit 1
fi

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 检查词典文件
if [ ! -f "dict/oaldpe.mdx" ]; then
    echo "[提示] dict/ 目录下未找到词典文件 oaldpe.mdx"
    echo "如需本地词典功能，请将朗文英汉词典文件放入 dict/ 目录后重新构建"
    echo ""
fi

# 构建镜像
echo "[1/3] 正在构建 Docker 镜像..."
docker build -t english-word-app:latest .
echo "[完成] 镜像构建成功"
echo ""

# 导出镜像
echo "[2/3] 正在导出镜像文件..."
OUTPUT_FILE="english-word-app_$(date +%Y%m%d).tar"
docker save english-word-app:latest -o "$OUTPUT_FILE"
echo "[完成] 已导出: $OUTPUT_FILE"
echo ""

# 显示文件信息
echo "[3/3] 文件信息:"
ls -lh "$OUTPUT_FILE"

echo ""
echo "============================================"
echo "  构建完成！"
echo "  在 NAS 上导入: docker load -i $OUTPUT_FILE"
echo "============================================"

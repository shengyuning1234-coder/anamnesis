@echo off
chcp 65001 >nul
echo ============================================
echo   英语单词背诵记忆系统 — 镜像构建与导出
echo ============================================
echo.

:: 检查 Docker 是否可用
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Docker，请先安装 Docker Desktop
    echo 下载地址: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

:: 切换到脚本所在目录（英语单词/）
cd /d "%~dp0"

:: 检查词典文件
if not exist "dict\oaldpe.mdx" (
    echo [提示] dict\ 目录下未找到词典文件 oaldpe.mdx
    echo 如需本地词典功能，请将朗文英汉词典文件放入 dict\ 目录后重新构建
    echo.
)

:: 构建镜像
echo [1/3] 正在构建 Docker 镜像...
docker build -t english-word-app:latest .
if %errorlevel% neq 0 (
    echo [错误] 镜像构建失败！
    pause
    exit /b 1
)
echo [完成] 镜像构建成功
echo.

:: 导出镜像为 tar 文件
echo [2/3] 正在导出镜像文件...
set OUTPUT_FILE=english-word-app_%date:~0,4%%date:~5,2%%date:~8,2%.tar
docker save english-word-app:latest -o "%OUTPUT_FILE%"
if %errorlevel% neq 0 (
    echo [错误] 镜像导出失败！
    pause
    exit /b 1
)
echo [完成] 已导出: %OUTPUT_FILE%
echo.

:: 显示文件大小
echo [3/3] 文件信息:
for %%A in ("%OUTPUT_FILE%") do echo   文件名: %%A  (大小: %%~zA 字节)

echo.
echo ============================================
echo   构建完成！将 %OUTPUT_FILE% 上传到 NAS
echo   然后参考 DEPLOY_NAS.md 导入镜像
echo ============================================
pause

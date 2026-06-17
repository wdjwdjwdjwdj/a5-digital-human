#!/bin/bash
# 一键环境搭建脚本

set -euo pipefail

echo "=== A5 景区导览AI数字人 - 环境搭建 ==="

echo "[1/4] 安装 Python 依赖..."
pip install -r requirements.txt

echo "[2/4] 配置环境变量..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  → 请编辑 .env 填入 API Key"
else
    echo "  → .env 已存在，跳过"
fi

echo "[3/4] 下载 ASR / Live2D 模型..."
python scripts/download_models.py

echo "[4/4] 运行测试..."
pytest tests/ -v

echo "=== 环境搭建完成 ==="
echo "启动服务：python main.py"
echo "管理后台：streamlit run admin/app.py"

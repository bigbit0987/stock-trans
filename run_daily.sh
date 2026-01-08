#!/bin/bash

# AlphaHunter 一键启动脚本 (Linux/Mac)
# ------------------------------------------

# 获取脚本所在目录
BASEDIR=$(dirname "$0")
cd "$BASEDIR"

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ 错误: 虚拟环境不存在，请先运行 'python3 -m venv .venv && pip install -r requirements.txt'"
    exit 1
fi

echo "=========================================="
echo "🚀 AlphaHunter 一键启动程序 (收盘任务)"
echo "=========================================="

echo "[$(date +%H:%M:%S)] [1/4] 正在更新 RPS 数据..."
python3 main.py update

echo ""
echo "[$(date +%H:%M:%S)] [2/4] 正在执行尾盘选股扫描..."
python3 main.py scan --push

echo ""
echo "[$(date +%H:%M:%S)] [3/4] 正在执行持仓健康巡检..."
python3 main.py check --push

echo ""
echo "[$(date +%H:%M:%S)] [4/4] 正在执行虚拟持仓卖点监控..."
python3 main.py virtual --push

echo ""
echo "=========================================="
echo "✅ 今日任务处理完成！"
echo "=========================================="

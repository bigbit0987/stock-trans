#!/bin/bash
# ============================================
# AlphaHunter macOS 全自动化定时安装脚本
# v2.2 - 包含策略验证功能
# ============================================

set -e

BASEDIR=$(dirname "$0")
cd "$BASEDIR"
PROJECT_DIR=$(pwd)

PLIST_PREFIX="com.alphahunter"
LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$PROJECT_DIR/logs"
PYTHON_PATH="$PROJECT_DIR/.venv/bin/python"
MAIN_SCRIPT="$PROJECT_DIR/main.py"

echo "==========================================="
echo "🚀 AlphaHunter 全自动化定时任务安装向导"
echo "==========================================="
echo ""
echo "📁 项目目录: $PROJECT_DIR"
echo ""

# 创建日志目录
mkdir -p "$LOG_DIR"

# 检查虚拟环境
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "❌ 错误: 虚拟环境不存在"
    echo "请先运行: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# 定义任务配置
# 格式: "任务名|命令参数|小时|分钟|描述"
TASKS=(
    # 早盘
    "premarket|premarket --push|9|22|集合竞价预警"
    # 盘中策略验证 (6次检查)
    "virtual1|virtual --push|9|45|策略验证 (开盘后)"
    "virtual2|virtual --push|10|30|策略验证 (上午)"
    "virtual3|virtual --push|11|15|策略验证 (午前)"
    "virtual4|virtual --push|13|15|策略验证 (午后)"
    "virtual5|virtual --push|14|00|策略验证 (下午)"
    "virtual6|virtual --push|14|45|策略验证 (尾盘前)"
    # 尾盘选股
    "scan1|scan --push|14|35|尾盘扫描 (第一次)"
    "scan2|scan --push|14|50|尾盘扫描 (第二次)"
    # 收盘后
    "performance|performance --update|15|30|更新效果追踪"
    "update|update|17|00|RPS 数据更新"
    "stats|virtual --stats|18|00|策略验证统计"
)

# 卸载旧任务
echo "⏳ 清理旧的定时任务..."
for task in "${TASKS[@]}"; do
    IFS='|' read -r name _ _ _ _ <<< "$task"
    plist_name="${PLIST_PREFIX}.${name}"
    plist_path="${LAUNCHAGENT_DIR}/${plist_name}.plist"
    
    if launchctl list | grep -q "$plist_name" 2>/dev/null; then
        launchctl unload "$plist_path" 2>/dev/null || true
    fi
    rm -f "$plist_path"
done

# 创建新任务
echo "📝 正在创建定时任务..."
echo ""

for task in "${TASKS[@]}"; do
    IFS='|' read -r name cmd hour minute desc <<< "$task"
    plist_name="${PLIST_PREFIX}.${name}"
    plist_path="${LAUNCHAGENT_DIR}/${plist_name}.plist"
    
    # 生成 plist 文件
    cat > "$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${plist_name}</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd ${PROJECT_DIR} && source .venv/bin/activate && python main.py ${cmd}</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${hour}</integer>
        <key>Minute</key>
        <integer>${minute}</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/${name}_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/${name}_stderr.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONPATH</key>
        <string>${PROJECT_DIR}</string>
    </dict>
</dict>
</plist>
EOF
    
    # 加载任务
    launchctl load "$plist_path"
    printf "   ✓ %02d:%02d - %s\n" "$hour" "$minute" "$desc"
done

echo ""
echo "==========================================="
echo "✅ 全自动化定时任务安装成功!"
echo "==========================================="
echo ""
echo "📌 任务时间表:"
echo "   ┌─────────┬────────────────────────────┐"
echo "   │  09:22  │  📢 集合竞价预警            │"
echo "   ├─────────┼────────────────────────────┤"
echo "   │  09:45  │  🧪 策略验证 (开盘后)       │"
echo "   │  10:30  │  🧪 策略验证 (上午)         │"
echo "   │  11:15  │  🧪 策略验证 (午前)         │"
echo "   │  13:15  │  🧪 策略验证 (午后)         │"
echo "   │  14:00  │  🧪 策略验证 (下午)         │"
echo "   │  14:45  │  🧪 策略验证 (尾盘前)       │"
echo "   ├─────────┼────────────────────────────┤"
echo "   │  14:35  │  🔍 尾盘扫描 (第一次)       │"
echo "   │  14:50  │  🔍 尾盘扫描 (第二次)       │"
echo "   ├─────────┼────────────────────────────┤"
echo "   │  15:30  │  📊 更新效果追踪            │"
echo "   │  17:00  │  � RPS 数据更新            │"
echo "   │  18:00  │  📋 策略验证统计            │"
echo "   └─────────┴────────────────────────────┘"
echo ""
echo "� 工作流程:"
echo "   1. 下午14:35/14:50 自动选股并推送钉钉"
echo "   2. 推荐股票自动加入虚拟持仓追踪"
echo "   3. 次日盘中每小时自动检查卖点"
echo "   4. 达到止盈/止损条件时钉钉提醒"
echo "   5. 自动记录涨跌结果用于统计"
echo ""
echo "�📂 日志目录: $LOG_DIR/"
echo ""
echo "🔧 常用命令:"
echo "   查看状态: launchctl list | grep alphahunter"
echo "   手动触发: launchctl start com.alphahunter.scan1"
echo "   查看统计: python main.py virtual --stats"
echo "   停止任务: ./uninstall_launchd.sh"
echo ""

#!/bin/bash
# ============================================
# AlphaHunter 定时任务卸载脚本
# ============================================

PLIST_PREFIX="com.alphahunter"
LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"

# 所有任务名
TASK_NAMES=("scan1" "scan2" "check" "update" "daily")

echo "==========================================="
echo "🗑️  AlphaHunter 定时任务卸载"
echo "==========================================="
echo ""

unloaded=0

for name in "${TASK_NAMES[@]}"; do
    plist_name="${PLIST_PREFIX}.${name}"
    plist_path="${LAUNCHAGENT_DIR}/${plist_name}.plist"
    
    if launchctl list | grep -q "$plist_name" 2>/dev/null; then
        launchctl unload "$plist_path" 2>/dev/null
        echo "   ✓ 已停止: $plist_name"
        ((unloaded++))
    fi
    
    if [ -f "$plist_path" ]; then
        rm "$plist_path"
    fi
done

echo ""
if [ $unloaded -gt 0 ]; then
    echo "✅ 已卸载 $unloaded 个定时任务"
else
    echo "ℹ️  未发现已安装的定时任务"
fi

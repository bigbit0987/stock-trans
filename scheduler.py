#!/usr/bin/env python
"""
定时任务调度器
"""
import os
import sys
import time
import subprocess
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config import SCHEDULER

# 任务定义
TASKS = {
    # === 早盘任务 ===
    'premarket': {
        'command': ['premarket', '--push'],
        'time': '09:22',
        'description': '集合竞价预警'
    },
    
    # === 盘中虚拟持仓监控 (策略验证) ===
    'virtual_am_1': {
        'command': ['virtual', '--push'],
        'time': '09:45',
        'description': '策略验证 (开盘后)'
    },
    'virtual_am_2': {
        'command': ['virtual', '--push'],
        'time': '10:30',
        'description': '策略验证 (上午)'
    },
    'virtual_am_3': {
        'command': ['virtual', '--push'],
        'time': '11:15',
        'description': '策略验证 (午前)'
    },
    'virtual_pm_1': {
        'command': ['virtual', '--push'],
        'time': '13:15',
        'description': '策略验证 (午后)'
    },
    'virtual_pm_2': {
        'command': ['virtual', '--push'],
        'time': '14:00',
        'description': '策略验证 (下午)'
    },
    'virtual_pm_3': {
        'command': ['virtual', '--push'],
        'time': '14:45',
        'description': '策略验证 (尾盘前)'
    },
    
    # === 尾盘任务 ===
    'scan_1': {
        'command': ['scan', '--push'],
        'time': SCHEDULER['scan_time_1'],
        'description': '尾盘扫描 (第一次)'
    },
    'scan_2': {
        'command': ['scan', '--push'],
        'time': SCHEDULER['scan_time_2'],
        'description': '尾盘扫描 (第二次)'
    },
    
    # === 收盘后任务 ===
    'performance': {
        'command': ['performance', '--update'],
        'time': '15:30',
        'description': '更新效果追踪'
    },
    'update_rps': {
        'command': ['update'],
        'time': SCHEDULER['update_rps_time'],
        'description': '更新 RPS 数据'
    },
    'weekly_report': {
        'command': ['virtual', '--stats'],
        'time': '18:00',
        'description': '策略验证统计'
    },
}


def run_task(command_list: list, desc: str):
    """通过 main.py 运行任务"""
    print(f"\n{'='*60}")
    print(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] {desc}")
    print(f"{'='*60}")
    
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, 'main.py')] + command_list
    subprocess.run(cmd)


def is_trading_day() -> bool:
    """判断是否为交易日（简化版：只判断周末）"""
    return datetime.now().weekday() < 5


def run_scheduler():
    """运行调度器"""
    print("=" * 60)
    print("📅 定时任务调度器")
    print("=" * 60)
    print("\n已配置任务:")
    for name, task in TASKS.items():
        print(f"  ✓ {task['time']} - {task['description']}")
    
    print("\n⏳ 等待任务执行... (Ctrl+C 停止)")
    
    try:
        import schedule
        
        for name, task in TASKS.items():
            schedule.every().day.at(task['time']).do(
                run_task, task['command'], task['description']
            )
        
        while True:
            if is_trading_day():
                schedule.run_pending()
            time.sleep(30)
            
    except ImportError:
        print("\n⚠️ 请安装 schedule: pip install schedule")
    except KeyboardInterrupt:
        print("\n\n⏹️ 调度器已停止")


def run_now(task_name: str):
    """立即运行指定任务"""
    if task_name in TASKS:
        task = TASKS[task_name]
        run_task(task['command'], task['description'])
    else:
        print(f"未知任务: {task_name}")
        print("可用任务:", list(TASKS.keys()))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='定时任务调度')
    parser.add_argument('--run', type=str, help='立即运行指定任务')
    parser.add_argument('--list', action='store_true', help='列出所有任务')
    
    args = parser.parse_args()
    
    if args.list:
        print("\n📋 任务列表:")
        for name, task in TASKS.items():
            print(f"  {name}: {task['time']} - {task['description']}")
    elif args.run:
        run_now(args.run)
    else:
        run_scheduler()

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
    'update_rps': {
        'script': 'update_rps.py',
        'time': SCHEDULER['update_rps_time'],
        'description': '更新 RPS 数据'
    },
    'scan_1': {
        'script': 'scan.py',
        'time': SCHEDULER['scan_time_1'],
        'description': '尾盘扫描 (第一次)'
    },
    'scan_2': {
        'script': 'scan.py',
        'time': SCHEDULER['scan_time_2'],
        'description': '尾盘扫描 (第二次)'
    }
}


def run_script(script: str, desc: str):
    """运行脚本"""
    print(f"\n{'='*60}")
    print(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] {desc}")
    print(f"{'='*60}")
    
    subprocess.run([sys.executable, os.path.join(PROJECT_ROOT, script)])


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
                run_script, task['script'], task['description']
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
        run_script(task['script'], task['description'])
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

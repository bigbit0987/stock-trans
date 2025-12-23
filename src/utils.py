"""
工具函数模块
包含日志、格式化等通用工具
"""
import logging
import os
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")


def clean_old_logs():
    """清理超过 30 天的旧日志"""
    try:
        if not os.path.exists(LOGS_DIR):
            return
        now = datetime.now()
        for filename in os.listdir(LOGS_DIR):
            file_path = os.path.join(LOGS_DIR, filename)
            if os.path.isfile(file_path) and filename.endswith('.log'):
                # 获取文件最后修改时间
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if (now - file_time).days > 30:
                    os.remove(file_path)
    except Exception:
        pass


def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """
    配置并返回一个 Logger
    """
    # 自动清理旧日志
    clean_old_logs()
    
    # 创建 logs 目录
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # 输出到文件 (带日期)
    filename = os.path.join(LOGS_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.log")
    file_handler = logging.FileHandler(filename, encoding='utf-8')
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 输出到控制台 (保持清爽，只显示消息)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def format_price(price: float) -> str:
    """格式化价格显示"""
    return f"{price:.2f}"


def format_pct(pct: float) -> str:
    """格式化百分比显示"""
    return f"{pct:+.2f}%"


def format_number(num: int) -> str:
    """格式化数字（添加千分位）"""
    return f"{num:,}"


# 全局 Logger 实例
logger = setup_logger("AlphaHunter")

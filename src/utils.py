"""
工具函数模块 (v2.4)
包含日志、格式化、文件锁、日期校验等通用工具
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import pandas as pd

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


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











# ============================================
# 日期校验工具 (v2.4 新增)
# 防止 MA5 计算时的"未来函数"错误
# ============================================

def is_trading_day(date: datetime = None) -> bool:
    """
    简单判断是否为交易日（周一至周五）
    注: 未考虑节假日，精确判断需要查询交易日历
    """
    if date is None:
        date = datetime.now()
    return date.weekday() < 5


def get_today_str(fmt: str = '%Y-%m-%d') -> str:
    """获取今日日期字符串"""
    return datetime.now().strftime(fmt)


def ensure_history_excludes_today(hist: pd.DataFrame, date_col: str = 'date') -> pd.DataFrame:
    """
    确保历史数据不包含今天的数据（防止 MA5 等指标计算时的时间偏移）
    
    这解决了分析报告中提到的核心 Bug:
    - 如果 Akshare 返回的数据已经包含今天，hist_closes[-4:] 会把"今天"算两次
    - 此函数会强制切片只保留到昨日的数据
    
    Args:
        hist: 包含日期列的 DataFrame
        date_col: 日期列名
    
    Returns:
        不包含今日数据的 DataFrame
    """
    if hist is None or hist.empty:
        return hist
    
    try:
        today_str = get_today_str()
        
        # 统一日期格式
        if date_col in hist.columns:
            hist = hist.copy()
            # 将日期列转换为字符串格式进行比较
            date_strs = pd.to_datetime(hist[date_col]).dt.strftime('%Y-%m-%d')
            
            # 如果最后一行是今天，则移除
            if date_strs.iloc[-1] == today_str:
                hist = hist.iloc[:-1]
                logger.debug(f"历史数据已移除今日({today_str})记录")
        
        return hist
    except Exception as e:
        logger.warning(f"日期校验失败: {e}")
        return hist





# ============================================
# 黑名单动态加载 (v2.4 新增)
# 支持运行时刷新，无需重启
# ============================================

_blacklist_cache: List[str] = []
_blacklist_mtime: float = 0


def load_blacklist_dynamic() -> List[str]:
    """
    动态加载黑名单（支持热重载）
    
    检查文件修改时间，如果文件有更新则重新加载
    """
    global _blacklist_cache, _blacklist_mtime
    
    blacklist_file = os.path.join(PROJECT_ROOT, 'config', 'blacklist.txt')
    
    try:
        if not os.path.exists(blacklist_file):
            return _blacklist_cache
        
        # 检查文件是否有更新
        current_mtime = os.path.getmtime(blacklist_file)
        if current_mtime == _blacklist_mtime and _blacklist_cache:
            return _blacklist_cache
        
        # 重新加载
        blacklist = []
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    code = line.split()[0] if line.split() else line
                    if code:
                        blacklist.append(code)
        
        _blacklist_cache = blacklist
        _blacklist_mtime = current_mtime
        
        if blacklist:
            logger.debug(f"黑名单已加载: {len(blacklist)} 只股票")
        
        return blacklist
        
    except Exception as e:
        logger.warning(f"加载黑名单失败: {e}")
        return _blacklist_cache


# 全局 Logger 实例
logger = setup_logger("AlphaHunter")

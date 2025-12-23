"""
选股策略模块
"""
import pandas as pd
from typing import List, Dict, Optional
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import STRATEGY, BLACKLIST


def filter_by_basic_conditions(df: pd.DataFrame) -> pd.DataFrame:
    """
    基础条件过滤
    """
    mask = (
        (df['涨跌幅'] > STRATEGY['pct_change_min']) & 
        (df['涨跌幅'] < STRATEGY['pct_change_max']) & 
        (df['换手率'] > STRATEGY['turnover_min']) &
        (df['换手率'] < STRATEGY['turnover_max']) &
        (df['量比'] > STRATEGY['volume_ratio_min']) &
        (df['振幅'] < STRATEGY['amplitude_max']) &
        (df['是阳线'] == True) &
        (~df['名称'].str.contains('ST|退|N'))
    )
    
    result = df[mask].copy()
    
    # 应用黑名单过滤
    if BLACKLIST:
        result = result[~result['代码'].isin(BLACKLIST)]
    
    return result


def check_ma5_condition(
    current_price: float, 
    hist_closes: List[float]
) -> tuple:
    """
    检查 MA5 条件
    
    Returns:
        (是否满足, MA5值, 乖离率)
    """
    if len(hist_closes) < 4:
        return False, 0, 1
    
    # 计算实时 MA5
    ma5 = (sum(hist_closes[-4:]) + current_price) / 5
    
    # 计算乖离率
    bias = abs(current_price - ma5) / ma5
    
    return bias <= STRATEGY['ma5_bias_max'], ma5, bias


def check_prev_day_condition(prev_close: float, prev_open: float, prev_pct: float) -> bool:
    """
    检查前一天条件（小阳线）
    """
    is_red = prev_close > prev_open
    is_small = 0 < prev_pct < 5
    return is_red and is_small


def classify_by_rps(rps: float) -> tuple:
    """
    根据 RPS 分类
    
    Returns:
        (分类标签, 操作建议)
    """
    if rps >= 90:
        return "⭐ 趋势核心", "可多拿几天，跌破5日线止损"
    elif rps >= 75:
        return "🔥 潜力股", "次日冲高可卖一半，留一半观察"
    else:
        return "📊 稳健标的", "次日冲高即走，赚个稳妥"


def generate_signal(
    code: str,
    name: str,
    current_price: float,
    pct_change: float,
    turnover: float,
    volume_ratio: float,
    amplitude: float,
    hist_closes: List[float],
    prev_close: float,
    prev_open: float,
    prev_pct: float,
    rps: float = 50
) -> Optional[Dict]:
    """
    生成交易信号
    
    Returns:
        信号字典，如果不符合条件返回 None
    """
    # 检查 MA5 条件
    ma5_ok, ma5, bias = check_ma5_condition(current_price, hist_closes)
    if not ma5_ok:
        return None
    
    # 检查前一天条件
    prev_ok = check_prev_day_condition(prev_close, prev_open, prev_pct)
    
    # RPS 过滤
    if rps < STRATEGY['rps_min']:
        return None
    
    # 分类
    category, suggestion = classify_by_rps(rps)
    
    return {
        '代码': code,
        '名称': name,
        '现价': current_price,
        '涨幅%': round(pct_change, 2),
        '换手%': round(turnover, 2),
        '量比': round(volume_ratio, 2),
        '振幅%': round(amplitude * 100, 2),
        'MA5': round(ma5, 2),
        '乖离%': round(bias * 100, 2),
        '连阳': "✓" if prev_ok else "",
        'RPS': round(rps, 1),
        '分类': category,
        '建议': suggestion
    }

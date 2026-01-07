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
    rps: float = 50,
    sector_rps: float = 50,
    rps_change: float = 0
) -> Optional[Dict]:
    """
    生成交易信号 (v2.4 增强版)
    
    新增参数:
        sector_rps: 板块内RPS排名
        rps_change: RPS较前一日变动
    
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
    
    # v2.4: 分类逻辑增强 - 结合板块RPS和RPS趋势
    category, suggestion = classify_by_rps_enhanced(rps, sector_rps, rps_change)
    
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
        '板块RPS': round(sector_rps, 1),
        'RPS变动': round(rps_change, 1),
        '分类': category,
        '建议': suggestion
    }


def classify_by_rps_enhanced(rps: float, sector_rps: float, rps_change: float) -> tuple:
    """
    根据 RPS 及衍生指标进行增强分类 (v2.4)
    
    策略:
    1. 全市场RPS高 + 板块RPS高 = 双强股，最优
    2. 全市场RPS高 + RPS上升趋势 = 强势突破，次优
    3. 板块RPS高但全市场一般 = 板块龙头，可关注轮动机会
    4. RPS在下降 = 警惕，可能是补跌
    
    Returns:
        (分类标签, 操作建议)
    """
    # 双强：全市场RPS>=90 且 板块RPS>=80
    if rps >= 90 and sector_rps >= 80:
        if rps_change > 5:
            return "🚀 爆发龙头", "强势股中的强势，可重仓持有，跌破5日线减仓"
        return "⭐ 双强核心", "市场+板块双强，可多拿几天，跌破5日线止损"
    
    # 全市场强势 + 上升趋势
    if rps >= 85:
        if rps_change > 3:
            return "🔥 趋势加速", "RPS持续走强，趋势良好，可持有"
        elif rps_change < -5:
            return "⚠️ 高位回落", "RPS走弱，注意风险，冲高减仓"
        return "⭐ 趋势核心", "全市场强势，可多拿几天，跌破5日线止损"
    
    # 板块龙头
    if sector_rps >= 85 and rps >= 70:
        return "💎 板块龙头", "板块内领先，关注板块轮动机会"
    
    # 潜力股
    if rps >= 75:
        if rps_change > 5:
            return "📈 潜力突破", "RPS快速上升，可能是启动信号"
        return "🔥 潜力股", "次日冲高可卖一半，留一半观察"
    
    # 稳健标的
    if rps_change > 0:
        return "📊 稳健向上", "RPS上升中，次日冲高可走"
    else:
        return "📊 稳健标的", "次日冲高即走，赚个稳妥"


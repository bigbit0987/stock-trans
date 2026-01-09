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
    使用配置文件中的阈值
    """
    is_red = prev_close > prev_open
    pct_min = STRATEGY.get('prev_day_pct_min', 0)
    pct_max = STRATEGY.get('prev_day_pct_max', 5)
    is_small = pct_min < prev_pct < pct_max
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
    rps_change: float = 0,
    rps20: float = 50,                # v2.5 新增: 短周期 RPS
    hist_volumes: List[float] = None, # v2.4 新增: 历史成交量数据
    tail_vol_ratio: float = 0         # v2.5 新增: 尾盘 15min 成交占比
) -> Optional[Dict]:
    """
    生成交易信号 (v2.4 增强版)
    
    v2.4 新增功能:
    1. 量价协同判断 - 区分"缩量蓄势"与"放量滞涨"
    2. 量价信号会影响分类和建议
    
    新增参数:
        sector_rps: 板块内RPS排名
        rps_change: RPS较前一日变动
        hist_volumes: 历史成交量数据（用于量价分析）
    
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
    
    # =========================================
    # v2.4 新增: 量价协同判断
    # =========================================
    volume_signal = analyze_volume_price_pattern(pct_change, volume_ratio, hist_volumes, hist_closes)
    
    # 如果检测到放量滞涨（危险信号），可以选择过滤或降级
    if volume_signal.get('pattern') == 'stagnant_with_volume':
        # 放量滞涨：涨幅很小(<1%)但量比很大(>2.5)
        # 这通常是主力对倒出货的信号，次日极容易低开
        # 策略：不过滤，但在分类中标注警告
        pass
    
    # v2.4: 分类逻辑增强 - 结合板块RPS、RPS趋势和量价信号
    category, suggestion = classify_by_rps_enhanced(
        rps, sector_rps, rps_change, 
        volume_signal  # v2.4: 传入量价信号
    )
    
    # v2.5.0: RPS 背离检测 (强势股退潮)
    from src.indicators import detect_rps_divergence
    div_info = detect_rps_divergence(rps, rps20)
    if div_info['is_divergence']:
        # 如果是严重的补跌风险，直接不产生信号
        if div_info['signal'] == '🚫 强势股补跌风险':
            return None
        # 否则更新分类和建议
        category = div_info['signal']
        suggestion = "短周期转弱，注意高位退潮风险，逢高离场"
    
    result = {
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
    
    # v2.4: 添加量价信号信息
    # v2.5.0: 尾盘吸筹检测
    if tail_vol_ratio > 15:
        result['量价形态'] = f"{result.get('量价形态', '')} ✨尾盘吸筹({tail_vol_ratio}%)".strip()
        result['量价评分'] = result.get('量价评分', 50) + 15
    
    return result


def analyze_volume_price_pattern(
    pct_change: float, 
    volume_ratio: float,
    hist_volumes: List[float] = None,
    hist_closes: List[float] = None
) -> Dict:
    """
    分析量价形态 (v2.4 新增)
    
    策略报告中的关键优化点:
    1. 缩量上涨（价格小涨 + 量比<1.0）= 主力控盘良好，次日爆发力强
    2. 放量滞涨（价格小涨<1% + 量比>2.5）= 主力对倒出货，次日容易低开
    3. 温和放量上涨 = 正常上涨趋势
    
    Returns:
        {
            'pattern': str,      # 形态类型
            'label': str,        # 显示标签
            'score': float,      # 量价评分 (0-100)
            'warning': str,      # 警告信息(如有)
        }
    """
    result = {
        'pattern': 'normal',
        'label': '',
        'score': 50,
        'warning': ''
    }
    
    try:
        # 1. 检测放量滞涨 (危险信号)
        if pct_change < 1.0 and volume_ratio > 2.5:
            result = {
                'pattern': 'stagnant_with_volume',
                'label': '⚠️放量滞涨',
                'score': 25,
                'warning': '涨幅小但量能巨大，可能是主力出货，次日易低开'
            }
            return result
        
        # 2. 检测缩量蓄势 (正向信号)
        if 0 < pct_change < 3.0 and volume_ratio < 1.0:
            result = {
                'pattern': 'shrinking_volume_rise',
                'label': '✨缩量蓄势',
                'score': 80,
                'warning': ''
            }
            return result
        
        # 3. 检测健康放量上涨
        if pct_change > 2.0 and 1.2 < volume_ratio < 2.5:
            result = {
                'pattern': 'healthy_volume_rise',
                'label': '📈健康放量',
                'score': 70,
                'warning': ''
            }
            return result
        
        # 4. 检测极度缩量 (可能是无人问津)
        if volume_ratio < 0.5:
            result = {
                'pattern': 'extremely_low_volume',
                'label': '💤极度缩量',
                'score': 40,
                'warning': '成交量过低，流动性风险'
            }
            return result
        
        # 5. 使用历史数据进行更深入分析
        if hist_volumes and hist_closes and len(hist_volumes) >= 5:
            # 计算近期量能趋势
            recent_vol_avg = sum(hist_volumes[-3:]) / 3
            prev_vol_avg = sum(hist_volumes[-6:-3]) / 3 if len(hist_volumes) >= 6 else recent_vol_avg
            
            # 量能收缩中且价格上涨
            if recent_vol_avg < prev_vol_avg * 0.7:
                recent_price_change = (hist_closes[-1] - hist_closes[-3]) / hist_closes[-3] * 100 if len(hist_closes) >= 3 else 0
                if recent_price_change > 0:
                    result = {
                        'pattern': 'continuous_shrink_rise',
                        'label': '🎯持续缩量涨',
                        'score': 85,
                        'warning': ''
                    }
                    return result
    
    except Exception:
        pass
    
    return result


def classify_by_rps_enhanced(
    rps: float, 
    sector_rps: float, 
    rps_change: float,
    volume_signal: Dict = None  # v2.4 新增: 量价信号
) -> tuple:
    """
    根据 RPS 及衍生指标进行增强分类 (v2.4)
    
    策略:
    1. 全市场RPS高 + 板块RPS高 = 双强股，最优
    2. 全市场RPS高 + RPS上升趋势 = 强势突破，次优
    3. 板块RPS高但全市场一般 = 板块龙头，可关注轮动机会
    4. RPS在下降 = 警惕，可能是补跌
    
    v2.4 新增:
    5. 量价协同判断 - 缩量蓄势加分，放量滞涨降级
    
    Returns:
        (分类标签, 操作建议)
    """
    if volume_signal is None:
        volume_signal = {}
    
    vol_pattern = volume_signal.get('pattern', 'normal')
    vol_warning = volume_signal.get('warning', '')
    
    # =========================================
    # v2.4: 放量滞涨优先处理（危险信号）
    # =========================================
    if vol_pattern == 'stagnant_with_volume':
        # 无论 RPS 多高，放量滞涨都是危险信号
        return "⚠️ 放量滞涨", f"量能巨大但涨幅小，可能是出货，建议观望。{vol_warning}"
    
    # =========================================
    # 正常分类逻辑（带量价加成）
    # =========================================
    
    # 缩量蓄势加成
    is_shrinking = vol_pattern in ['shrinking_volume_rise', 'continuous_shrink_rise']
    shrink_bonus = " + 缩量蓄势" if is_shrinking else ""
    
    # 双强：全市场RPS>=90 且 板块RPS>=80
    if rps >= 90 and sector_rps >= 80:
        if rps_change > 5:
            base = "🚀 爆发龙头"
            suggestion = "强势股中的强势，可重仓持有，跌破5日线减仓"
        else:
            base = "⭐ 双强核心"
            suggestion = "市场+板块双强，可多拿几天，跌破5日线止损"
        
        if is_shrinking:
            suggestion = "【量价共振】" + suggestion + "，缩量蓄势爆发力更强"
        
        return base + shrink_bonus, suggestion
    
    # 全市场强势 + 上升趋势
    if rps >= 85:
        if rps_change > 3:
            return "🔥 趋势加速" + shrink_bonus, "RPS持续走强，趋势良好，可持有"
        elif rps_change < -5:
            return "⚠️ 高位回落", "RPS走弱，注意风险，冲高减仓"
        return "⭐ 趋势核心" + shrink_bonus, "全市场强势，可多拿几天，跌破5日线止损"
    
    # 板块龙头
    if sector_rps >= 85 and rps >= 70:
        return "💎 板块龙头" + shrink_bonus, "板块内领先，关注板块轮动机会"
    
    # 潜力股
    if rps >= 75:
        if rps_change > 5:
            return "📈 潜力突破" + shrink_bonus, "RPS快速上升，可能是启动信号"
        return "🔥 潜力股" + shrink_bonus, "次日冲高可卖一半，留一半观察"
    
    # 稳健标的
    if rps_change > 0:
        return "📊 稳健向上" + shrink_bonus, "RPS上升中，次日冲高可走"
    else:
        return "📊 稳健标的", "次日冲高即走，赚个稳妥"


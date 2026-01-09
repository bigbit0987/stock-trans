"""
技术指标计算模块
v2.3 增强版 - 包含ATR止损、凯利公式等
"""
import pandas as pd
import numpy as np
from typing import Optional, List, Dict
import os
import json
from datetime import datetime





def detect_rps_divergence(rps120: float, rps20: float) -> Dict:
    """
    检测 RPS 长短周期背离 (v2.5 新增)
    
    逻辑：如果长周期 (RPS120) 极强，但短周期 (RPS20) 跌破阈值，说明强势股陷入退潮/补跌。
    
    Returns:
        {
            'is_divergence': bool,
            'signal': str,         # 'RETREAT' (退潮), 'NORMAL'
            'score_adjustment': int
        }
    """
    if rps120 > 90 and rps20 < 70:
        return {
            'is_divergence': True,
            'signal': '⚠️ 高位退潮',
            'score_adjustment': -20
        }
    elif rps120 > 85 and rps20 < 60:
        return {
            'is_divergence': True,
            'signal': '🚫 强势股补跌风险',
            'score_adjustment': -30
        }
    return {'is_divergence': False, 'signal': 'NORMAL', 'score_adjustment': 0}









# ============================================
# ATR (平均真实波幅) - v2.3 新增
# ============================================




def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """
    计算 ATR (Average True Range)
    
    ATR = SMA(TR, period)
    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    
    Returns:
        ATR值
    """
    if len(highs) < period + 1:
        return 0
    
    trs = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)
    
    if len(trs) >= period:
        atr = sum(trs[-period:]) / period
    else:
        atr = sum(trs) / len(trs) if trs else 0
    
    return round(atr, 3)


def calculate_atr_stop_loss(buy_price: float, atr: float, multiplier: float = 2.0) -> float:
    """
    计算基于ATR的动态止损位
    
    顶级CTA基金的保命符：
    - 波动大的股票止损宽一些
    - 波动小的股票止损紧一些
    
    Args:
        buy_price: 买入价
        atr: 当前ATR
        multiplier: ATR倍数 (默认2倍)
    
    Returns:
        止损价位
    """
    return round(buy_price - atr * multiplier, 2)


def get_grade_based_stop_params(grade: str = 'B') -> Dict:
    """
    根据股票评级获取差异化的止损/止盈参数 (v2.5 策略师建议)
    
    - Grade A (趋势核心): 容忍度高 (1.5倍-2倍 ATR)，博取主升浪。
    - Grade C (稳健/杂毛): 容忍度低 (1.2倍 ATR)，移动止盈更敏感。
    """
    params = {
        'A': {'atr_multiplier': 2.0, 'drawdown_threshold': -5.0, 'take_profit': 15.0},
        'B': {'atr_multiplier': 1.5, 'drawdown_threshold': -3.0, 'take_profit': 10.0},
        'C': {'atr_multiplier': 1.2, 'drawdown_threshold': -2.5, 'take_profit': 5.0},
    }
    return params.get(grade, params['B'])





# ============================================
# 凯利公式仓位管理 - v2.3 新增
# ============================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADE_HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "virtual_trades.json")


def load_recent_trades(days: int = 30) -> List[Dict]:
    """加载最近N天的交易记录"""
    if not os.path.exists(TRADE_HISTORY_FILE):
        return []
    
    try:
        with open(TRADE_HISTORY_FILE, 'r', encoding='utf-8') as f:
            trades = json.load(f)
        
        # 过滤最近N天
        cutoff = datetime.now().timestamp() - days * 24 * 3600
        recent = []
        for t in trades:
            try:
                trade_date = datetime.strptime(t['sell_date'][:10], '%Y-%m-%d')
                if trade_date.timestamp() >= cutoff:
                    recent.append(t)
            except (KeyError, ValueError, TypeError):
                # 跳过格式不正确的交易记录
                continue
        return recent
    except (json.JSONDecodeError, IOError) as e:
        return []


def calculate_win_rate(trades: List[Dict]) -> float:
    """计算胜率"""
    if not trades:
        return 0.5  # 默认50%
    
    wins = sum(1 for t in trades if t.get('pnl_pct', 0) > 0)
    return wins / len(trades)


def calculate_profit_loss_ratio(trades: List[Dict]) -> float:
    """计算盈亏比"""
    if not trades:
        return 1.0
    
    profits = [t['pnl_pct'] for t in trades if t.get('pnl_pct', 0) > 0]
    losses = [abs(t['pnl_pct']) for t in trades if t.get('pnl_pct', 0) < 0]
    
    avg_profit = sum(profits) / len(profits) if profits else 0
    avg_loss = sum(losses) / len(losses) if losses else 1
    
    return avg_profit / avg_loss if avg_loss > 0 else 1.0


def kelly_criterion(win_rate: float, profit_loss_ratio: float) -> float:
    """
    凯利公式计算最优仓位比例
    
    f* = (bp - q) / b
    
    其中:
    - b = 盈亏比
    - p = 胜率
    - q = 败率 (1-p)
    
    Returns:
        建议仓位比例 (0-1)
    """
    p = win_rate
    q = 1 - p
    b = profit_loss_ratio
    
    kelly = (b * p - q) / b
    
    # 安全调整：实际使用一半凯利值
    half_kelly = kelly / 2
    
    # 限制范围
    return max(0.1, min(0.5, half_kelly))


def calculate_dynamic_position_size(base_amount: float, trades: List[Dict] = None) -> Dict:
    """
    根据历史表现动态计算仓位
    
    Args:
        base_amount: 基础单笔金额
        trades: 历史交易记录 (可选，默认自动加载)
    
    Returns:
        {
            'suggested_amount': float,   # 建议金额
            'win_rate': float,          # 历史胜率
            'kelly_ratio': float,       # 凯利比例
            'adjustment': str,          # 调整说明
        }
    """
    if trades is None:
        trades = load_recent_trades(30)
    
    if len(trades) < 5:
        # 样本太少，保守处理
        return {
            'suggested_amount': base_amount * 0.5,
            'win_rate': 0.5,
            'kelly_ratio': 0.5,
            'adjustment': '样本不足，使用一半仓位',
        }
    
    win_rate = calculate_win_rate(trades)
    pl_ratio = calculate_profit_loss_ratio(trades)
    kelly = kelly_criterion(win_rate, pl_ratio)
    
    # 根据胜率调整
    if win_rate >= 0.7:
        adjustment = '胜率优秀，可加大仓位'
        multiplier = 1.5
    elif win_rate >= 0.55:
        adjustment = '胜率良好，正常仓位'
        multiplier = 1.0
    elif win_rate >= 0.4:
        adjustment = '胜率一般，减少仓位'
        multiplier = 0.7
    else:
        adjustment = '胜率较低，最小仓位'
        multiplier = 0.3
    
    suggested = base_amount * kelly * multiplier
    
    # 限制在合理范围
    suggested = max(base_amount * 0.2, min(base_amount * 2.0, suggested))
    
    return {
        'suggested_amount': round(suggested, 0),
        'win_rate': round(win_rate, 3),
        'kelly_ratio': round(kelly, 3),
        'adjustment': adjustment,
    }


# ============================================
# 板块强弱滤网 - v2.3 新增
# ============================================

def get_sector_rank(sector_name: str, all_sectors: List[Dict]) -> Optional[int]:
    """
    获取板块在全市场的排名
    """
    for s in all_sectors:
        if s['name'] in sector_name or sector_name in s['name']:
            return s['rank']
    return None


def is_sector_strong(sector_name: str, all_sectors: List[Dict], threshold: float = 0.33) -> bool:
    """
    判断板块是否处于全市场前1/3
    
    Args:
        sector_name: 板块名称
        all_sectors: 所有板块排名列表
        threshold: 阈值 (默认前1/3)
    
    Returns:
        是否强势板块
    """
    if not all_sectors:
        return True  # 数据不足时不过滤
    
    total = len(all_sectors)
    rank = get_sector_rank(sector_name, all_sectors)
    
    if rank is None:
        return False
    
    return rank <= total * threshold


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


def calculate_ma(series: pd.Series, window: int) -> pd.Series:
    """计算移动平均线"""
    return series.rolling(window).mean()


def calculate_bias(price: pd.Series, ma: pd.Series) -> pd.Series:
    """计算乖离率"""
    return (price - ma) / ma


def calculate_amplitude(high: pd.Series, low: pd.Series, prev_close: pd.Series) -> pd.Series:
    """计算振幅"""
    return (high - low) / prev_close


def calculate_rps(momentum_series: pd.Series) -> pd.Series:
    """
    计算 RPS (相对强度排名)
    返回 0-100 的百分位排名
    """
    return momentum_series.rank(pct=True) * 100


def calculate_realtime_ma5(current_price: float, last_4_closes: list) -> float:
    """
    计算实时 MA5
    用于盘中计算（当天收盘价未确定时）
    """
    if len(last_4_closes) < 4:
        return current_price
    return (sum(last_4_closes[-4:]) + current_price) / 5


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    为 DataFrame 添加技术指标
    
    Args:
        df: 包含 OHLCV 数据的 DataFrame
            需要的列: 开盘, 收盘, 最高, 最低, 成交量
    
    Returns:
        添加了技术指标的 DataFrame
    """
    df = df.copy()
    
    # 均线
    df['MA5'] = calculate_ma(df['收盘'], 5)
    df['MA10'] = calculate_ma(df['收盘'], 10)
    df['MA20'] = calculate_ma(df['收盘'], 20)
    
    # 涨跌幅
    df['涨跌幅'] = df['收盘'].pct_change() * 100
    
    # 乖离率
    df['MA5乖离'] = abs(calculate_bias(df['收盘'], df['MA5']))
    
    # 振幅
    df['振幅'] = calculate_amplitude(df['最高'], df['最低'], df['收盘'].shift(1))
    
    # 阳线/阴线
    df['是阳线'] = df['收盘'] > df['开盘']
    
    # 量比
    df['量比'] = df['成交量'] / df['成交量'].rolling(5).mean()
    
    # 动量 (N日涨幅)
    df['动量_20'] = df['收盘'].pct_change(20)
    df['动量_60'] = df['收盘'].pct_change(60)
    df['动量_120'] = df['收盘'].pct_change(120)
    
    # ATR (v2.3 新增)
    df['ATR'] = calculate_atr_series(df['最高'], df['最低'], df['收盘'])
    
    return df


def check_consecutive_red(df: pd.DataFrame, days: int = 2) -> pd.Series:
    """
    检查是否连续 N 天阳线
    """
    is_red = df['收盘'] > df['开盘']
    return is_red.rolling(days).sum() == days


def is_near_ma(price: float, ma: float, threshold: float = 0.02) -> bool:
    """
    判断价格是否贴近均线
    """
    if ma == 0:
        return False
    bias = abs(price - ma) / ma
    return bias <= threshold


# ============================================
# ATR (平均真实波幅) - v2.3 新增
# ============================================

def calculate_atr_series(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    计算 ATR 序列
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


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


# ============================================
# RSI (相对强弱指数) - v2.3 新增
# ============================================

def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """
    计算 RSI
    
    RSI > 70: 超买
    RSI < 30: 超卖
    
    Returns:
        RSI值 (0-100)
    """
    if len(closes) < period + 1:
        return 50
    
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) >= period:
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 1)
    
    return 50


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
            except:
                pass
        return recent
    except:
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


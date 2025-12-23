"""
技术指标计算模块
"""
import pandas as pd
import numpy as np
from typing import Optional


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

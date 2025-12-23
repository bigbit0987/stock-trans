#!/usr/bin/env python
"""
数据获取模块 - 优化版
支持缓存、重试、批量获取
"""
import akshare as ak
import pandas as pd
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Callable

# 导入配置
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import STRATEGY, RPS_DATA_DIR, CONCURRENT, NETWORK, CACHE
from src.cache_manager import cache_manager
from src.utils import logger


def retry_on_failure(max_retries: int = 3, delay: float = 0.5):
    """重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))  # 指数退避
            return None
        return wrapper
    return decorator


def get_all_stocks() -> pd.DataFrame:
    """获取全市场 A 股列表"""
    logger.info("📡 获取全市场股票列表...")
    df = ak.stock_zh_a_spot_em()
    
    # 过滤 ST、退市、新股
    df = df[~df['名称'].str.contains('ST|退|N')]
    
    logger.info(f"   共 {len(df)} 只股票")
    return df


def get_realtime_quotes() -> pd.DataFrame:
    """获取实时行情数据"""
    logger.info("📡 获取实时行情...")
    df = ak.stock_zh_a_spot_em()
    
    # 计算振幅
    df['振幅'] = (df['最高'] - df['最低']) / df['昨收'] 
    
    # 判断阳线
    df['是阳线'] = df['最新价'] > df['今开']
    
    logger.info(f"   获取到 {len(df)} 只股票")
    return df


@retry_on_failure(max_retries=NETWORK.get('max_retries', 3), delay=NETWORK.get('retry_delay', 0.5))
def _fetch_stock_history_from_api(code: str, days: int = 150, adjust: str = "qfq") -> Optional[pd.DataFrame]:
    """从API获取股票历史数据（带重试）"""
    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust=adjust)
    if df is None or len(df) < days:
        return None
    return df.tail(days + 10)


def get_stock_history(code: str, days: int = 30, adjust: str = "qfq", use_cache: bool = True) -> Optional[pd.DataFrame]:
    """
    获取单只股票的历史数据（带缓存）
    
    Args:
        code: 股票代码
        days: 获取天数
        adjust: 复权类型 (qfq=前复权, hfq=后复权, ""=不复权)
        use_cache: 是否使用缓存
    """
    # 1. 尝试从缓存获取
    if use_cache and CACHE.get('enabled', True):
        cached = cache_manager.get_cached_history(code, days)
        if cached is not None and len(cached) >= days:
            return cached.tail(days + 10)
    
    # 2. 从API获取
    try:
        df = _fetch_stock_history_from_api(code, days, adjust)
        
        if df is not None and use_cache:
            # 保存到缓存
            cache_manager.save_history_cache(code, df)
        
        return df
    except Exception as e:
        return None


def get_stock_history_range(
    code: str, 
    start_date: str, 
    end_date: str, 
    adjust: str = "qfq"
) -> Optional[pd.DataFrame]:
    """获取指定日期范围的历史数据"""
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, 
            period="daily", 
            start_date=start_date,
            end_date=end_date,
            adjust=adjust
        )
        return df if len(df) > 0 else None
    except:
        return None


def batch_get_history(
    codes: List[str], 
    days: int = 30,
    progress_callback: Callable = None,
    use_cache: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    批量获取历史数据（多线程 + 缓存）
    """
    results = {}
    processed = 0
    total = len(codes)
    cache_hits = 0
    
    # 先检查缓存
    codes_to_fetch = []
    if use_cache and CACHE.get('enabled', True):
        for code in codes:
            cached = cache_manager.get_cached_history(code, days)
            if cached is not None and len(cached) >= days:
                results[code] = cached.tail(days + 10)
                cache_hits += 1
            else:
                codes_to_fetch.append(code)
    else:
        codes_to_fetch = codes
    
    if cache_hits > 0:
        logger.info(f"   📦 缓存命中: {cache_hits}/{total}")
    
    # 从API获取剩余数据
    if codes_to_fetch:
        max_workers = CONCURRENT.get('max_workers', 30)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(get_stock_history, code, days, "qfq", use_cache): code 
                for code in codes_to_fetch
            }
            
            for future in as_completed(futures):
                code = futures[future]
                processed += 1
                
                try:
                    df = future.result()
                    if df is not None:
                        results[code] = df
                except Exception as e:
                    pass
                
                if progress_callback and processed % 100 == 0:
                    progress_callback(processed + cache_hits, total)
    
    return results


def load_latest_rps() -> Optional[pd.DataFrame]:
    """加载最新的 RPS 数据"""
    if not os.path.exists(RPS_DATA_DIR):
        return None
    
    files = sorted([f for f in os.listdir(RPS_DATA_DIR) if f.startswith('rps_rank_')])
    if not files:
        return None
    
    latest_file = files[-1]
    filepath = os.path.join(RPS_DATA_DIR, latest_file)
    
    logger.info(f"📖 加载 RPS 数据: {latest_file}")
    df = pd.read_csv(filepath)
    df['代码'] = df['代码'].astype(str).str.zfill(6)
    
    return df


def get_cached_momentum(code: str) -> Optional[dict]:
    """获取缓存的动量数据（供scanner使用）"""
    return cache_manager.get_momentum(code)


def get_cache_stats() -> dict:
    """获取缓存统计"""
    return cache_manager.get_cache_stats()

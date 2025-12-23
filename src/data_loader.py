"""
数据获取模块
统一管理股票数据的获取
"""
import akshare as ak
import pandas as pd
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict

# 导入配置
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import STRATEGY, RPS_DATA_DIR, CONCURRENT


def get_all_stocks() -> pd.DataFrame:
    """获取全市场 A 股列表"""
    print("📡 获取全市场股票列表...")
    df = ak.stock_zh_a_spot_em()
    
    # 过滤 ST、退市、新股
    df = df[~df['名称'].str.contains('ST|退|N')]
    
    print(f"   共 {len(df)} 只股票")
    return df


def get_realtime_quotes() -> pd.DataFrame:
    """获取实时行情数据"""
    print("📡 获取实时行情...")
    df = ak.stock_zh_a_spot_em()
    
    # 计算振幅
    df['振幅'] = (df['最高'] - df['最低']) / df['昨收'] 
    
    # 判断阳线
    df['是阳线'] = df['最新价'] > df['今开']
    
    print(f"   获取到 {len(df)} 只股票")
    return df


def get_stock_history(code: str, days: int = 30, adjust: str = "qfq") -> Optional[pd.DataFrame]:
    """
    获取单只股票的历史数据
    
    Args:
        code: 股票代码
        days: 获取天数
        adjust: 复权类型 (qfq=前复权, hfq=后复权, "=不复权)
    """
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust=adjust)
        if len(df) < days:
            return None
        return df.tail(days + 10)  # 多取一些用于计算均线
    except Exception as e:
        return None


def get_stock_history_range(
    code: str, 
    start_date: str, 
    end_date: str, 
    adjust: str = "qfq"
) -> Optional[pd.DataFrame]:
    """
    获取指定日期范围的历史数据
    """
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
    progress_callback=None
) -> Dict[str, pd.DataFrame]:
    """
    批量获取历史数据（多线程）
    """
    results = {}
    processed = 0
    total = len(codes)
    
    with ThreadPoolExecutor(max_workers=CONCURRENT['max_workers']) as executor:
        futures = {
            executor.submit(get_stock_history, code, days): code 
            for code in codes
        }
        
        for future in as_completed(futures):
            code = futures[future]
            processed += 1
            
            df = future.result()
            if df is not None:
                results[code] = df
            
            if progress_callback and processed % 100 == 0:
                progress_callback(processed, total)
    
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
    
    print(f"📖 加载 RPS 数据: {latest_file}")
    df = pd.read_csv(filepath)
    df['symbol'] = df['symbol'].astype(str).str.zfill(6)
    
    return df

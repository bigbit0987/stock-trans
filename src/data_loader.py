#!/usr/bin/env python
"""
数据获取模块 (v2.4 增强版)
功能:
1. 智能缓存 + 批量获取
2. tenacity 指数退避重试（网络鲁棒性）
3. 日期校验（防止 MA5 等指标的未来函数错误）
"""
import akshare as ak
import pandas as pd
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Callable

# tenacity 重试库
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

# 导入配置
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import STRATEGY, RPS_DATA_DIR, CONCURRENT, NETWORK, CACHE
from src.cache_manager import cache_manager
from src.utils import logger, ensure_history_excludes_today

# ============================================
# 数据源标准映射 (v2.5.0: 解决 Akshare 字段变动问题)
# ============================================

# 实时行情字段映射
REALTIME_COL_MAP = {
    '代码': 'code',
    '名称': 'name',
    '最新价': 'close',
    '今开': 'open',
    '最高': 'high',
    '最低': 'low',
    '成交量': 'volume',
    '成交额': 'amount',
    '涨跌幅': 'pct_change',
    '换手率': 'turnover',
    '量比': 'volume_ratio',
    '市盈率-动态': 'pe',
    '市净率': 'pb',
    '总市值': 'market_cap',
}

# 历史行情字段映射
HIST_COL_MAP = {
    '日期': 'date',
    '开盘': 'open',
    '收盘': 'close',
    '最高': 'high',
    '最低': 'low',
    '成交量': 'volume',
    '成交额': 'amount',
    '振幅': 'amplitude',
    '涨跌幅': 'pct_change',
    '换手率': 'turnover',
}

def standardize_df(df: pd.DataFrame, col_map: Dict[str, str]) -> pd.DataFrame:
    """
    统一 DataFrame 列名，增强系统抗波动能力
    """
    if df is None or df.empty:
        return df
    return df.rename(columns=col_map)


# ============================================
# 智能重试装饰器 (v2.4 tenacity 增强版)
# ============================================

def retry_on_failure(max_retries: int = 3, delay: float = 0.5):
    """
    智能重试装饰器
    
    v2.4 增强:
    - 使用 tenacity 实现更专业的指数退避
    - 自动识别可重试的异常类型
    - 超时保护
    """
    def decorator(func):
        if HAS_TENACITY:
            # 使用 tenacity 的指数退避重试
            @retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=delay, min=0.5, max=10),
                retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
                reraise=True
            )
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        else:
            # 降级使用简单重试
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
    """获取实时行情数据并标准化 (v2.5.0)"""
    logger.info("📡 获取实时行情...")
    df = ak.stock_zh_a_spot_em()
    
    # 标准化列名
    df = standardize_df(df, REALTIME_COL_MAP)
    
    # ---【v2.5.0 兼容性增强：保留中文索引副本】---
    # 这样既能让旧代码跑通，又能让新逻辑使用英文标准列
    compat_map = {v: k for k, v in REALTIME_COL_MAP.items()}
    for eng, chn in compat_map.items():
        if eng in df.columns:
            df[chn] = df[eng]
    
    # 补充计算字段的标准化映射
    if 'high' in df.columns and 'low' in df.columns and 'close' in df.columns:
        df['amplitude'] = (df['high'] - df['low']) / df['close'].shift(1).fillna(df['open'])
        df['振幅'] = df['amplitude']
        df['is_up'] = df['close'] > df['open']
        df['是阳线'] = df['is_up']
    
    logger.info(f"   获取到 {len(df)} 只股票")
    return df


@retry_on_failure(max_retries=NETWORK.get('max_retries', 3), delay=NETWORK.get('retry_delay', 0.5))
def get_tail_volume_ratio(code: str) -> float:
    """
    计算尾盘 15 分钟成交量占比 (v2.5.0)
    
    逻辑：
    1. 获取当日 1 分钟数据
    2. 计算 14:45 - 15:00 的成交量总和
    3. 计算全天成交量总和
    4. 返回比例
    """
    try:
        df = ak.stock_zh_a_hist_min_em(symbol=code, period='1', adjust='qfq')
        if df is None or df.empty:
            return 0.0
        
        # 确保时间是字符串并过滤当日数据
        today_str = datetime.datetime.now().strftime('%Y-%m-%d')
        # 如果是夜间测试或非交易日，取最后一天
        last_date = df.iloc[-1]['时间'].split(' ')[0]
        df_today = df[df['时间'].str.startswith(last_date)]
        
        if df_today.empty:
            return 0.0
            
        total_volume = df_today['成交量'].sum()
        # 取最后 15 根 K 线
        tail_df = df_today.tail(15)
        tail_volume = tail_df['成交量'].sum()
        
        if total_volume > 0:
            return round(tail_volume / total_volume * 100, 2)
        return 0.0
    except Exception as e:
        logger.debug(f"获取 {code} 尾盘数据失败: {e}")
        return 0.0


@retry_on_failure(max_retries=NETWORK.get('max_retries', 3), delay=NETWORK.get('retry_delay', 0.5))
def _fetch_stock_history_from_api(code: str, days: int = 150, adjust: str = "qfq") -> Optional[pd.DataFrame]:
    """
    从API获取股票历史数据（带重试）
    
    v2.4 增强: 使用 tenacity 指数退避重试
    """
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20200101", adjust=adjust)
        if df is None or df.empty:
            return None
        
        # 标准化列名 (v2.5.0)
        df = standardize_df(df, HIST_COL_MAP)
        
        # 统一日期格式
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            
        return df.tail(days + 10)
    except Exception as e:
        logger.error(f"获取 {code} 历史数据 API 失败: {e}")
        return None


def get_stock_history(
    code: str, 
    days: int = 30, 
    adjust: str = "qfq", 
    use_cache: bool = True,
    exclude_today: bool = True  # v2.4 新增: 是否排除今日数据
) -> Optional[pd.DataFrame]:
    """
    获取单只股票的历史数据（带缓存 + 日期校验）
    
    Args:
        code: 股票代码
        days: 获取天数
        adjust: 复权类型 (qfq=前复权, hfq=后复权, ""=不复权)
        use_cache: 是否使用缓存
        exclude_today: 是否排除今日数据（防止 MA5 等指标计算错误）
    
    v2.4 增强:
    - 自动排除今日数据，避免 MA5 计算时的"未来函数"错误
    - 使用 tenacity 增强网络重试
    """
    # 1. 尝试从缓存获取
    if use_cache and CACHE.get('enabled', True):
        cached = cache_manager.get_cached_history(code, days)
        if cached is not None and len(cached) >= days:
            df = cached.tail(days + 10)
            # v2.4: 日期校验，排除今日
            if exclude_today:
                df = ensure_history_excludes_today(df)
            return df
    
    # 2. 从API获取
    try:
        df = _fetch_stock_history_from_api(code, days, adjust)
        
        if df is not None:
            # v2.4: 日期校验，排除今日
            if exclude_today:
                df = ensure_history_excludes_today(df)
            
            if use_cache:
                # 保存到缓存（保存原始数据，不含今日校验）
                cache_manager.save_history_cache(code, df)
        
        return df
    except Exception as e:
        logger.debug(f"获取 {code} 历史数据失败: {e}")
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
    except Exception:
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


def get_all_sector_mappings(use_cache: bool = True) -> Dict[str, str]:
    """
    获取全市场股票的板块映射 (Code -> SectorName)
    
    策略:
    1. 优先读取本地缓存 (data/sector_map.json)
    2. 如果缓存过期(>7天)或强制刷新, 则从API获取
    3. API获取方式: 获取所有板块名称 -> 并发获取每个板块的成分股 -> 构建映射
    """
    import json
    
    SECTOR_MAP_FILE = os.path.join(RPS_DATA_DIR, "sector_map.json")
    
    # 1. 尝试读取缓存
    if use_cache and os.path.exists(SECTOR_MAP_FILE):
        try:
            # 检查文件时间
            mtime = os.path.getmtime(SECTOR_MAP_FILE)
            if time.time() - mtime < 7 * 24 * 3600: # 7天有效期
                with open(SECTOR_MAP_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError, OSError):
            pass
            
    logger.info("📡 正在全量更新板块数据 (大概需要 1-2 分钟)...")
    
    mapping = {}
    try:
        # 获取所有行业板块
        boards = ak.stock_board_industry_name_em()
        if boards is None or boards.empty:
            return {}
            
        board_names = boards['板块名称'].tolist()
        
        # 并发获取板块成分股
        def _get_cons(name):
            try:
                df = ak.stock_board_industry_cons_em(symbol=name)
                if df is not None and not df.empty:
                    return name, df['代码'].tolist()
            except Exception:
                return name, []
            return name, []

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_board = {executor.submit(_get_cons, name): name for name in board_names}
            
            processed = 0
            for future in as_completed(future_to_board):
                name, codes = future.result()
                for code in codes:
                    # 一个股票可能属于多个板块吗？东方财富的行业板块通常是主行业
                    # 这里简单的覆盖，或者保留第一个
                    if code not in mapping:
                        mapping[code] = name
                
                processed += 1
                if processed % 10 == 0:
                    print(f"\r   进度: {processed}/{len(board_names)}", end="")
        
        print("") # new line
        
        # 保存缓存
        os.makedirs(os.path.dirname(SECTOR_MAP_FILE), exist_ok=True)
        with open(SECTOR_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False)
            
        logger.info(f"   ✅ 板块数据更新完成，共 {len(mapping)} 只股票归类")
        return mapping
        
    except Exception as e:
        logger.error(f"   ❌ 获取板块数据失败: {e}")
        # 如果失败且有旧缓存，尝试读取旧缓存
        if os.path.exists(SECTOR_MAP_FILE):
            try:
                with open(SECTOR_MAP_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

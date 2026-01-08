#!/usr/bin/env python
"""
统一缓存管理模块
提供高效的股票历史数据缓存，支持增量更新
"""
import os
import sys
import json
import pickle
import datetime
import pandas as pd
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import CACHE, DATA_DIR
from src.utils import logger

# 缓存目录
CACHE_DIR = os.path.join(DATA_DIR, "cache")
HISTORY_CACHE_DIR = os.path.join(CACHE_DIR, "history")
MOMENTUM_CACHE_FILE = os.path.join(CACHE_DIR, "momentum_cache.pkl")

# 确保目录存在
for d in [CACHE_DIR, HISTORY_CACHE_DIR]:
    os.makedirs(d, exist_ok=True)


class CacheManager:
    """
    股票数据缓存管理器
    
    特性:
    1. 日内缓存: 当天计算过的数据缓存到内存
    2. 本地缓存: 历史数据缓存到本地文件
    3. 增量更新: 只获取最新一天数据，其他从历史缓存读取
    """
    
    def __init__(self):
        self._memory_cache: Dict[str, pd.DataFrame] = {}
        self._momentum_cache: Dict[str, dict] = {}
        self._cache_date: str = ""
        self._load_momentum_cache()
    
    def _get_today_str(self) -> str:
        """获取今天日期字符串"""
        return datetime.date.today().strftime("%Y%m%d")
    
    def _load_momentum_cache(self):
        """加载动量缓存"""
        if os.path.exists(MOMENTUM_CACHE_FILE):
            try:
                with open(MOMENTUM_CACHE_FILE, 'rb') as f:
                    cache_data = pickle.load(f)
                    cache_date = cache_data.get('date', '')
                    
                    # 只加载当天的缓存
                    if cache_date == self._get_today_str():
                        self._momentum_cache = cache_data.get('data', {})
                        self._cache_date = cache_date
                        logger.info(f"📦 加载动量缓存: {len(self._momentum_cache)} 只股票")
                    else:
                        logger.info(f"📦 动量缓存已过期 ({cache_date})，将重新计算")
            except Exception as e:
                logger.warning(f"动量缓存加载失败: {e}")
    
    def save_momentum_cache(self):
        """保存动量缓存"""
        try:
            cache_data = {
                'date': self._get_today_str(),
                'data': self._momentum_cache,
                'updated_at': datetime.datetime.now().isoformat()
            }
            with open(MOMENTUM_CACHE_FILE, 'wb') as f:
                pickle.dump(cache_data, f)
            logger.info(f"💾 动量缓存已保存: {len(self._momentum_cache)} 只股票")
        except Exception as e:
            logger.warning(f"动量缓存保存失败: {e}")
    
    def get_momentum(self, code: str) -> Optional[dict]:
        """获取缓存的动量数据"""
        if self._cache_date != self._get_today_str():
            return None
        return self._momentum_cache.get(code)
    
    def set_momentum(self, code: str, data: dict):
        """设置动量缓存"""
        self._momentum_cache[code] = data
        self._cache_date = self._get_today_str()
    
    def get_history_cache_path(self, code: str) -> str:
        """获取历史数据缓存文件路径"""
        return os.path.join(HISTORY_CACHE_DIR, f"{code}.parquet")
    
    def get_cached_history(self, code: str, days: int = 150) -> Optional[pd.DataFrame]:
        """
        获取缓存的历史数据
        
        Returns:
            DataFrame 或 None
        """
        cache_path = self.get_history_cache_path(code)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            df = pd.read_parquet(cache_path)
            
            # 检查数据是否足够新（最后一条数据的日期）
            if len(df) > 0:
                last_date = pd.to_datetime(df['日期'].iloc[-1])
                today = datetime.date.today()
                
                # 如果数据是今天或昨天的，认为有效
                days_diff = (today - last_date.date()).days
                if days_diff <= 1:
                    return df.tail(days + 10)  # 多返回一些用于计算
            
            return None
        except Exception as e:
            return None
    
    def save_history_cache(self, code: str, df: pd.DataFrame):
        """保存历史数据到缓存"""
        if df is None or len(df) == 0:
            return
        
        try:
            cache_path = self.get_history_cache_path(code)
            df.to_parquet(cache_path, index=False)
        except Exception as e:
            logger.warning(f"历史缓存保存失败 {code}: {e}")
    
    def needs_update(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        检查股票是否需要更新
        
        Returns:
            (需要更新, 上次更新日期)
        """
        cache_path = self.get_history_cache_path(code)
        
        if not os.path.exists(cache_path):
            return True, None
        
        try:
            df = pd.read_parquet(cache_path)
            if len(df) == 0:
                return True, None
            
            last_date = pd.to_datetime(df['日期'].iloc[-1]).strftime('%Y%m%d')
            today = datetime.date.today().strftime('%Y%m%d')
            
            # 如果最后日期不是今天，需要更新
            return last_date != today, last_date
        except Exception:
            return True, None
    
    def get_all_cached_codes(self) -> List[str]:
        """获取所有已缓存的股票代码"""
        codes = []
        for f in os.listdir(HISTORY_CACHE_DIR):
            if f.endswith('.parquet'):
                codes.append(f.replace('.parquet', ''))
        return codes
    
    def cleanup_old_cache(self, max_days: int = 7):
        """清理过期缓存"""
        try:
            import time
            now = time.time()
            max_age = max_days * 24 * 3600
            
            removed = 0
            for f in os.listdir(HISTORY_CACHE_DIR):
                fpath = os.path.join(HISTORY_CACHE_DIR, f)
                if os.path.isfile(fpath):
                    age = now - os.path.getmtime(fpath)
                    if age > max_age:
                        os.remove(fpath)
                        removed += 1
            
            if removed > 0:
                logger.info(f"🧹 清理了 {removed} 个过期缓存文件")
        except Exception as e:
            logger.warning(f"缓存清理失败: {e}")
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        history_count = len(self.get_all_cached_codes())
        momentum_count = len(self._momentum_cache)
        
        # 计算缓存大小
        total_size = 0
        for f in os.listdir(HISTORY_CACHE_DIR):
            fpath = os.path.join(HISTORY_CACHE_DIR, f)
            if os.path.isfile(fpath):
                total_size += os.path.getsize(fpath)
        
        return {
            'history_cached': history_count,
            'momentum_cached': momentum_count,
            'cache_size_mb': round(total_size / 1024 / 1024, 2),
            'cache_date': self._cache_date
        }


# 全局缓存管理器实例
cache_manager = CacheManager()

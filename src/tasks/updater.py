#!/usr/bin/env python
"""
RPS 数据更新任务 - 高性能版本
特性:
1. 智能缓存: 支持日内缓存和历史数据持久化
2. 增量更新: 只获取缺失/过期的数据
3. 批量处理: 分批处理避免内存溢出
4. 实时进度: 显示速度和预估剩余时间
"""
import os
import sys
import datetime
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config.settings import STRATEGY, RPS_DATA_DIR, CONCURRENT, NETWORK, CACHE
from src.cache_manager import cache_manager
from src.utils import logger


def get_stock_momentum_fast(code: str, name: str) -> Optional[Dict]:
    """
    快速获取股票动量数据
    1. 先检查动量缓存
    2. 再检查历史数据缓存
    3. 最后从API获取
    """
    window = STRATEGY.get('rps_window', 120)
    
    # 1. 检查动量缓存（最快）
    cached_momentum = cache_manager.get_momentum(code)
    if cached_momentum:
        return cached_momentum
    
    # 2. 检查历史数据缓存
    df = cache_manager.get_cached_history(code, window + 10)
    
    # 3. 如果缓存未命中或过期，从API获取
    if df is None or len(df) < window:
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df is not None and len(df) > 0:
                # 保存到历史缓存
                cache_manager.save_history_cache(code, df)
        except Exception as e:
            return None
    
    # 4. 计算动量
    if df is None or len(df) < window:
        return None
    
    try:
        close_now = df['收盘'].iloc[-1]
        close_prev = df['收盘'].iloc[-window]
        pct_change = (close_now - close_prev) / close_prev
        
        # 保存最近4天收盘价，供实时计算MA5
        last_4_closes = df['收盘'].tail(4).tolist()
        
        result = {
            '代码': code,
            '名称': name,
            'momentum': pct_change,
            '最新价': close_now,
            'MA5': df['收盘'].tail(5).mean(),
            'last_4_closes_sum': sum(last_4_closes)
        }
        
        # 保存到动量缓存
        cache_manager.set_momentum(code, result)
        
        return result
    except Exception as e:
        return None


def run_updater():
    """执行 RPS 数据更新（高性能版）"""
    logger.info("=" * 60)
    logger.info("📊 RPS 数据更新启动 (高性能版)")
    logger.info(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   周期: {STRATEGY.get('rps_window', 120)} 天")
    logger.info(f"   并发: {CONCURRENT.get('max_workers', 30)} 线程")
    logger.info("=" * 60)
    
    # 显示缓存状态
    stats = cache_manager.get_cache_stats()
    logger.info(f"\n📦 缓存状态:")
    logger.info(f"   历史数据缓存: {stats['history_cached']} 只")
    logger.info(f"   动量缓存: {stats['momentum_cached']} 只")
    logger.info(f"   缓存大小: {stats['cache_size_mb']} MB")
    
    # 获取股票列表
    logger.info("\n📡 获取全市场股票列表...")
    stock_info = ak.stock_zh_a_spot_em()
    stock_info = stock_info[['代码', '名称']]
    # 过滤掉 ST、退市和新股
    stock_info = stock_info[~stock_info['名称'].str.contains('ST|退|N')]
    
    total = len(stock_info)
    logger.info(f"   共 {total} 只标的")
    
    # 分批处理
    batch_size = CONCURRENT.get('batch_size', 100)
    max_workers = CONCURRENT.get('max_workers', 30)
    all_results = []
    
    logger.info(f"\n🔄 正在计算个股动量...")
    logger.info(f"   批次大小: {batch_size}, 并发线程: {max_workers}")
    
    start_time = time.time()
    cache_hits = 0
    api_calls = 0
    
    for batch_idx in range(0, total, batch_size):
        batch_end = min(batch_idx + batch_size, total)
        batch_df = stock_info.iloc[batch_idx:batch_end]
        
        batch_results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(get_stock_momentum_fast, row['代码'], row['名称']): row['代码']
                for _, row in batch_df.iterrows()
            }
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    batch_results.append(result)
        
        all_results.extend(batch_results)
        
        # 计算并显示进度
        elapsed = time.time() - start_time
        processed = len(all_results)
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = (total - batch_end) / rate if rate > 0 else 0
        
        # 每5批显示一次进度
        if (batch_idx // batch_size) % 5 == 0 or batch_end == total:
            logger.info(
                f"   [{batch_end}/{total}] "
                f"{batch_end*100//total}% | "
                f"速度: {rate:.1f}只/秒 | "
                f"剩余: {remaining:.0f}秒"
            )
    
    # 保存动量缓存
    cache_manager.save_momentum_cache()
    
    # 计算 RPS 排名
    if not all_results:
        logger.error("\n❌ 未获取到有效数据，计算终止")
        return
    
    rps_df = pd.DataFrame(all_results)
    # 计算百分比排名
    rps_df['RPS'] = rps_df['momentum'].rank(pct=True) * 100
    rps_df = rps_df.sort_values(by='RPS', ascending=False)
    
    # 保存结果
    today = datetime.date.today().strftime("%Y%m%d")
    os.makedirs(RPS_DATA_DIR, exist_ok=True)
    filepath = os.path.join(RPS_DATA_DIR, f"rps_rank_{today}.csv")
    rps_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    # 计算统计信息
    total_time = time.time() - start_time
    
    logger.info(f"\n✅ RPS 数据更新完成!")
    logger.info(f"   文件: {filepath}")
    logger.info(f"   有效数据: {len(rps_df)} 只")
    logger.info(f"   处理速度: {len(all_results)/total_time:.1f} 只/秒")
    logger.info(f"   总耗时: {total_time:.1f} 秒 ({total_time/60:.1f} 分钟)")
    
    logger.info("\n📈 RPS 强度前 15 名:")
    print_df = rps_df[['代码', '名称', 'RPS', 'momentum']].head(15)
    logger.info(print_df.to_string(index=False))
    logger.info("=" * 60)
    
    return rps_df


if __name__ == "__main__":
    start = datetime.datetime.now()
    run_updater()
    duration = (datetime.datetime.now() - start).seconds
    logger.info(f"\n⏱️ 总耗时: {duration // 60} 分 {duration % 60} 秒")

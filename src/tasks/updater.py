#!/usr/bin/env python
"""
RPS 数据更新任务
每天收盘后运行，计算全市场股票的相对强度排名
"""
import os
import sys
import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config import STRATEGY, RPS_DATA_DIR, CONCURRENT
from src.utils import logger


def get_stock_momentum(code: str, name: str) -> dict:
    """获取单只股票的动量数据"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        
        window = STRATEGY.get('rps_window', 120)
        if len(df) < window:
            return None
        
        close_now = df['收盘'].iloc[-1]
        close_prev = df['收盘'].iloc[-window]
        pct_change = (close_now - close_prev) / close_prev
        
        # 保存最近4天收盘价，供实时计算MA5
        last_4_closes = df['收盘'].tail(4).tolist()
        
        return {
            '代码': code,
            '名称': name,
            'momentum': pct_change,
            '最新价': close_now,
            'MA5': df['收盘'].tail(5).mean(),
            'last_4_closes_sum': sum(last_4_closes)
        }
    except:
        return None


def run_updater():
    """执行 RPS 数据更新"""
    logger.info("=" * 60)
    logger.info("📊 RPS 数据更新启动")
    logger.info(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   周期: {STRATEGY.get('rps_window', 120)} 天")
    logger.info("=" * 60)
    
    # 获取股票列表
    logger.info("\n📡 获取全市场股票列表...")
    stock_info = ak.stock_zh_a_spot_em()
    stock_info = stock_info[['代码', '名称']]
    # 过滤掉 ST、退市和新股
    stock_info = stock_info[~stock_info['名称'].str.contains('ST|退|N')]
    
    total = len(stock_info)
    logger.info(f"   共 {total} 只标的")
    
    # 多线程获取数据
    rps_list = []
    processed = 0
    
    logger.info("\n🔄 正在计算个股动量 (这可能需要几分钟)...")
    
    max_workers = CONCURRENT.get('max_workers', 10)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(get_stock_momentum, row['代码'], row['名称']): row['代码']
            for _, row in stock_info.iterrows()
        }
        
        for future in as_completed(futures):
            processed += 1
            result = future.result()
            if result:
                rps_list.append(result)
            
            if processed % 500 == 0:
                logger.info(f"   进度: {processed}/{total} ({processed*100//total}%)")
    
    # 计算 RPS 排名
    if not rps_list:
        logger.error("\n❌ 未获取到有效数据，计算终止")
        return
    
    rps_df = pd.DataFrame(rps_list)
    # 计算百分比排名
    rps_df['RPS'] = rps_df['momentum'].rank(pct=True) * 100
    rps_df = rps_df.sort_values(by='RPS', ascending=False)
    
    # 保存结果
    today = datetime.date.today().strftime("%Y%m%d")
    os.makedirs(RPS_DATA_DIR, exist_ok=True)
    filepath = os.path.join(RPS_DATA_DIR, f"rps_rank_{today}.csv")
    rps_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    logger.info(f"\n✅ RPS 数据更新完成: {filepath}")
    logger.info(f"   有效数据共 {len(rps_df)} 只")
    
    logger.info("\n📈 RPS 强度前 15 名:")
    print_df = rps_df[['代码', '名称', 'RPS', 'momentum']].head(15)
    logger.info(print_df.to_string(index=False))
    logger.info("=" * 60)


if __name__ == "__main__":
    start = datetime.datetime.now()
    run_updater()
    duration = (datetime.datetime.now() - start).seconds
    logger.info(f"\n⏱️ 总耗时: {duration // 60} 分 {duration % 60} 秒")

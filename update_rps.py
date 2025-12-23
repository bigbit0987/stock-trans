#!/usr/bin/env python
"""
RPS 数据更新
每天收盘后运行，计算全市场股票的相对强度排名
"""
import os
import sys
import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config import STRATEGY, RPS_DATA_DIR, CONCURRENT


def get_stock_momentum(code: str, name: str) -> dict:
    """获取单只股票的动量数据"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        
        window = STRATEGY['rps_window']
        if len(df) < window:
            return None
        
        close_now = df['收盘'].iloc[-1]
        close_prev = df['收盘'].iloc[-window]
        pct_change = (close_now - close_prev) / close_prev
        
        # 保存最近4天收盘价，供实时计算MA5
        last_4_closes = df['收盘'].tail(4).tolist()
        
        return {
            'symbol': code,
            'name': name,
            'momentum': pct_change,
            'close': close_now,
            'ma5': df['收盘'].tail(5).mean(),
            'last_4_closes_sum': sum(last_4_closes)
        }
    except:
        return None


def update_rps():
    """更新 RPS 数据"""
    print("=" * 60)
    print("📊 RPS 数据更新")
    print(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   周期: {STRATEGY['rps_window']} 天")
    print("=" * 60)
    
    # 获取股票列表
    print("\n📡 获取股票列表...")
    stock_info = ak.stock_zh_a_spot_em()
    stock_info = stock_info[['代码', '名称']]
    stock_info = stock_info[~stock_info['名称'].str.contains('ST|退|N')]
    
    total = len(stock_info)
    print(f"   共 {total} 只股票")
    
    # 多线程获取数据
    rps_list = []
    processed = 0
    
    print("\n🔄 正在计算动量...")
    
    with ThreadPoolExecutor(max_workers=CONCURRENT['max_workers']) as executor:
        futures = {
            executor.submit(get_stock_momentum, row['代码'], row['名称']): row['代码']
            for _, row in stock_info.iterrows()
        }
        
        for future in as_completed(futures):
            processed += 1
            result = future.result()
            if result:
                rps_list.append(result)
            
            if processed % 200 == 0:
                print(f"   已处理 {processed}/{total} ({processed*100//total}%)")
    
    # 计算 RPS 排名
    if not rps_list:
        print("\n❌ 未获取到有效数据")
        return
    
    rps_df = pd.DataFrame(rps_list)
    rps_df['rps'] = rps_df['momentum'].rank(pct=True) * 100
    rps_df = rps_df.sort_values(by='rps', ascending=False)
    
    # 保存
    today = datetime.date.today().strftime("%Y%m%d")
    filepath = os.path.join(RPS_DATA_DIR, f"rps_rank_{today}.csv")
    rps_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ RPS 数据已更新: {filepath}")
    print(f"   共计算 {len(rps_df)} 只股票")
    print("\n📈 RPS 前20名:")
    print(rps_df[['symbol', 'name', 'rps', 'momentum']].head(20).to_string(index=False))


if __name__ == "__main__":
    start = datetime.datetime.now()
    update_rps()
    duration = (datetime.datetime.now() - start).seconds
    print(f"\n⏱️ 耗时: {duration // 60} 分 {duration % 60} 秒")

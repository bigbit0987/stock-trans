#!/usr/bin/env python
"""
策略回测
"""
import os
import sys
import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config import STRATEGY, BACKTEST, BACKTEST_DIR, CONCURRENT


def get_history(code: str) -> pd.DataFrame:
    """获取历史数据"""
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, 
            period="daily", 
            start_date='20230601',
            end_date=BACKTEST['end_date'],
            adjust="qfq"
        )
        return df if len(df) > 150 else None
    except:
        return None


def simulate_trades(df: pd.DataFrame, code: str) -> list:
    """模拟交易"""
    if df is None or len(df) < 150:
        return []
    
    df = df.copy()
    
    # 计算指标
    df['MA5'] = df['收盘'].rolling(5).mean()
    df['涨跌幅'] = df['收盘'].pct_change() * 100
    df['是阳线'] = df['收盘'] > df['开盘']
    df['前日阳线'] = df['是阳线'].shift(1)
    df['前日涨幅'] = df['涨跌幅'].shift(1)
    df['MA5乖离'] = abs(df['收盘'] - df['MA5']) / df['MA5']
    df['振幅'] = (df['最高'] - df['最低']) / df['收盘'].shift(1)
    df['动量_120'] = df['收盘'].pct_change(120)
    
    df = df.dropna()
    
    # 过滤日期范围
    df['日期_str'] = pd.to_datetime(df['日期']).dt.strftime('%Y%m%d')
    df = df[(df['日期_str'] >= BACKTEST['start_date']) & 
            (df['日期_str'] <= BACKTEST['end_date'])]
    
    if len(df) < 10:
        return []
    
    df = df.reset_index(drop=True)
    trades = []
    
    for i in range(len(df) - 1):
        row = df.iloc[i]
        
        # 买入条件
        if not (
            STRATEGY['pct_change_min'] < row['涨跌幅'] < STRATEGY['pct_change_max'] and
            row['是阳线'] and row['前日阳线'] and
            0 < row['前日涨幅'] < 5 and
            row['MA5乖离'] < STRATEGY['ma5_bias_max'] and
            row['振幅'] < STRATEGY['amplitude_max']
        ):
            continue
        
        # 动量过滤
        if pd.isna(row['动量_120']) or row['动量_120'] < 0:
            continue
        
        # 模拟交易
        buy_price = row['收盘']
        next_row = df.iloc[i + 1]
        sell_price = next_row['开盘']
        
        gross_ret = (sell_price - buy_price) / buy_price
        cost = BACKTEST['commission'] * 2 + BACKTEST['stamp_duty']
        net_ret = gross_ret - cost
        
        trades.append({
            'code': code,
            'buy_date': row['日期'],
            'sell_date': next_row['日期'],
            'buy_price': buy_price,
            'sell_price': sell_price,
            'momentum': row['动量_120'],
            'net_return': net_ret,
            'win': net_ret > 0
        })
    
    return trades


def run_backtest():
    """运行回测"""
    print("=" * 60)
    print("📊 策略回测")
    print(f"   区间: {BACKTEST['start_date']} ~ {BACKTEST['end_date']}")
    print("=" * 60)
    
    # 获取股票列表
    print("\n📡 获取股票列表...")
    stock_info = ak.stock_zh_a_spot_em()
    stock_info = stock_info[~stock_info['名称'].str.contains('ST|退|N')]
    codes = stock_info['代码'].tolist()[:BACKTEST['sample_size']]
    
    print(f"   抽样 {len(codes)} 只股票")
    
    # 获取数据并回测
    all_trades = []
    processed = 0
    
    print("\n🔄 正在回测...")
    
    with ThreadPoolExecutor(max_workers=CONCURRENT['max_workers']) as executor:
        futures = {executor.submit(get_history, code): code for code in codes}
        
        for future in as_completed(futures):
            code = futures[future]
            processed += 1
            
            df = future.result()
            trades = simulate_trades(df, code)
            all_trades.extend(trades)
            
            if processed % 100 == 0:
                print(f"   已处理 {processed}/{len(codes)}")
    
    if not all_trades:
        print("\n❌ 无交易信号")
        return
    
    # 统计
    trades_df = pd.DataFrame(all_trades)
    total = len(trades_df)
    wins = trades_df['win'].sum()
    
    print("\n" + "=" * 60)
    print("📈 回测结果")
    print("=" * 60)
    print(f"""
    交易次数: {total}
    盈利次数: {wins}
    胜率:     {wins/total*100:.2f}%
    平均收益: {trades_df['net_return'].mean()*100:+.2f}%
    最大盈利: {trades_df['net_return'].max()*100:+.2f}%
    最大亏损: {trades_df['net_return'].min()*100:+.2f}%
    """)
    
    # 保存
    filename = f"回测_{BACKTEST['start_date']}_{BACKTEST['end_date']}.csv"
    filepath = os.path.join(BACKTEST_DIR, filename)
    trades_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"💾 详细记录: {filepath}")


if __name__ == "__main__":
    start = datetime.datetime.now()
    run_backtest()
    duration = (datetime.datetime.now() - start).seconds
    print(f"\n⏱️ 耗时: {duration // 60} 分 {duration % 60} 秒")

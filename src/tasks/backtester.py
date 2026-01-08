#!/usr/bin/env python
"""
策略回测任务
用于历史回溯验证策略收益和胜率
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
from config import STRATEGY, BACKTEST, BACKTEST_DIR, CONCURRENT
from src.utils import logger


def get_history(code: str) -> pd.DataFrame:
    """获取股票的历史 K 线数据"""
    try:
        # 为了计算动量和 MA5，需要比回测开始日期更早的数据
        df = ak.stock_zh_a_hist(
            symbol=code, 
            period="daily", 
            start_date='20230601',
            end_date=BACKTEST.get('end_date', '20241220'),
            adjust="qfq"
        )
        return df if (df is not None and len(df) > 150) else None
    except Exception:
        return None


def simulate_trades(df: pd.DataFrame, code: str) -> list:
    """在给定个股数据上模拟交易"""
    if df is None or len(df) < 150:
        return []
    
    df = df.copy()
    
    # 计算技术指标
    df['MA5'] = df['收盘'].rolling(5).mean()
    df['涨跌幅'] = df['收盘'].pct_change() * 100
    df['是阳线'] = df['收盘'] > df['开盘']
    df['前日阳线'] = df['是阳线'].shift(1)
    df['前日涨幅'] = df['涨跌幅'].shift(1)
    df['MA5乖离'] = abs(df['收盘'] - df['MA5']) / df['MA5']
    df['振幅'] = (df['最高'] - df['最低']) / df['收盘'].shift(1)
    df['动量_120'] = df['收盘'].pct_change(120)
    
    df = df.dropna()
    
    # 根据回测配置过滤日期范围
    df['日期_str'] = pd.to_datetime(df['日期']).dt.strftime('%Y%m%d')
    start_dt = BACKTEST.get('start_date', '20240101')
    end_dt = BACKTEST.get('end_date', '20241220')
    df = df[(df['日期_str'] >= start_dt) & (df['日期_str'] <= end_dt)]
    
    if len(df) < 2:
        return []
    
    df = df.reset_index(drop=True)
    trades = []
    
    # 模拟“尾盘进，次日开盘出”策略
    for i in range(len(df) - 1):
        row = df.iloc[i]
        
        # 核心选股条件过滤
        if not (
            STRATEGY['pct_change_min'] < row['涨跌幅'] < STRATEGY['pct_change_max'] and
            row['是阳线'] and row['前日阳线'] and
            0 < row['前日涨幅'] < 5 and
            row['MA5乖离'] < STRATEGY.get('ma5_bias_max', 0.02) and
            row['振幅'] < STRATEGY.get('amplitude_max', 0.05)
        ):
            continue
        
        # 动量过滤 (模拟强度排名后的简单过滤)
        if pd.isna(row['动量_120']) or row['动量_120'] < 0:
            continue
        
        # 模拟交易逻辑
        buy_price = row['收盘']
        next_row = df.iloc[i + 1]
        sell_price = next_row['开盘']
        
        # 计算毛利和净利 (扣除滑点和交易成本)
        gross_ret = (sell_price - buy_price) / buy_price
        cost = BACKTEST.get('commission', 0.0003) * 2 + BACKTEST.get('stamp_duty', 0.001)
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


def run_backtester():
    """执行回测并打印结果"""
    logger.info("=" * 60)
    logger.info("📈 策略回测启动")
    logger.info(f"   区间: {BACKTEST.get('start_date')} ~ {BACKTEST.get('end_date')}")
    logger.info("=" * 60)
    
    # 获取回测用的股票池
    logger.info("\n📡 准备股票池...")
    stock_info = ak.stock_zh_a_spot_em()
    stock_info = stock_info[~stock_info['名称'].str.contains('ST|退|N')]
    
    sample_size = BACKTEST.get('sample_size', 500)
    codes = stock_info['代码'].tolist()[:sample_size]
    
    logger.info(f"   抽样测试 {len(codes)} 只证券标的")
    
    all_trades = []
    processed = 0
    
    max_workers = CONCURRENT.get('max_workers', 10)
    
    logger.info("\n🔄 扫描历史行情并执行模拟交易...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {executor.submit(get_history, code): code for code in codes}
        
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            processed += 1
            
            try:
                df = future.result()
                trades = simulate_trades(df, code)
                all_trades.extend(trades)
            except Exception as e:
                logger.error(f"   ⚠️ 处理 {code} 时出错: {e}")
            
            if processed % 100 == 0:
                logger.info(f"   进度: {processed}/{len(codes)}")
    
    if not all_trades:
        logger.warning("\n❌ 测试期间无任何交易信号产生")
        return
    
    # 结果统计数据
    trades_df = pd.DataFrame(all_trades)
    total_trades = len(trades_df)
    wins = trades_df['win'].sum()
    win_rate = wins / total_trades if total_trades > 0 else 0
    avg_ret = trades_df['net_return'].mean()
    
    logger.info("\n" + "=" * 60)
    logger.info("📈 策略回测报告")
    logger.info("=" * 60)
    logger.info(f"  总成交笔数: {total_trades}")
    logger.info(f"  成功笔数:   {wins}")
    logger.info(f"  策略胜率:   {win_rate:.2%}")
    logger.info(f"  平均单笔净盈亏: {avg_ret:.2%}")
    logger.info(f"  最大单笔利润:   {trades_df['net_return'].max():.2%}")
    logger.info(f"  最大单笔亏损:   {trades_df['net_return'].min():.2%}")
    
    # 保存明细
    os.makedirs(BACKTEST_DIR, exist_ok=True)
    filename = f"回测报告_{BACKTEST['start_date']}_{BACKTEST['end_date']}.csv"
    filepath = os.path.join(BACKTEST_DIR, filename)
    trades_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    logger.info(f"\n📂 交易明细已保存至: {filepath}")
    logger.info("-" * 60)


if __name__ == "__main__":
    start = datetime.datetime.now()
    run_backtester()
    duration = (datetime.datetime.now() - start).seconds
    logger.info(f"\n⏱️ 执行耗时: {duration // 60} 分 {duration % 60} 秒")

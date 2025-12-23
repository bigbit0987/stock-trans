#!/usr/bin/env python
"""
尾盘选股扫描
建议在 14:35 - 14:50 运行
"""
import os
import sys
import datetime
import pandas as pd

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import STRATEGY, RESULTS_DIR, CONCURRENT, RISK_CONTROL
from src.data_loader import get_realtime_quotes, load_latest_rps, get_stock_history
from src.strategy import filter_by_basic_conditions, generate_signal


def check_market_risk(realtime_df: pd.DataFrame = None) -> tuple:
    """
    检查大盘风险 (增强版: 指数 + 涨跌家数)
    
    Args:
        realtime_df: 可选，如果已经获取了实时行情，直接复用
    
    Returns:
        (是否安全, 上证涨跌幅, 赚钱效应)
    """
    try:
        # 1. 指数跌幅
        index_df = ak.stock_zh_index_spot_em()
        sh_idx = index_df[index_df['代码'] == '000001']
        sh_pct = sh_idx.iloc[0]['涨跌幅'] if not sh_idx.empty else 0
        
        # 2. 市场情绪（涨跌家数）
        if realtime_df is not None:
            market_df = realtime_df
        else:
            market_df = ak.stock_zh_a_spot_em()
        
        up_count = len(market_df[market_df['涨跌幅'] > 0])
        down_count = len(market_df[market_df['涨跌幅'] < 0])
        total = up_count + down_count
        
        # 赚钱效应: 上涨家数占比
        sentiment = up_count / total if total > 0 else 0.5
        
        print(f"   上证指数: {sh_pct:+.2f}%")
        print(f"   涨/跌家数: {up_count}/{down_count} (赚钱效应: {sentiment:.0%})")
        
        # 使用配置文件中的阈值
        drop_threshold = RISK_CONTROL.get('market_drop_threshold', -1.5)
        sentiment_threshold = RISK_CONTROL.get('sentiment_threshold', 0.2)
        
        # 判定逻辑: 指数大跌 OR 全场普跌
        is_safe = (sh_pct > drop_threshold) and (sentiment > sentiment_threshold)
        
        return is_safe, sh_pct, sentiment
        
    except Exception as e:
        print(f"   ⚠️ 风控检查出错: {e}")
        print(f"   ⚠️ 默认返回"不安全"，请检查网络")
        return False, 0, 0  # 风控失败时默认不安全！


def run_scan():
    """运行尾盘扫描"""
    print("=" * 60)
    print("🚀 尾盘选股扫描")
    print(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 检查是否周末
    weekday = datetime.datetime.today().weekday()
    if weekday >= 5:
        print("\n⚠️ 警告：今天是周末，A股不开市，数据可能未更新！")
    
    # 获取实时行情 (先获取，用于风控和筛选)
    df = get_realtime_quotes()
    
    # 检查大盘风险 (复用已获取的数据)
    print("\n📊 检查大盘状态...")
    is_safe, sh_pct, sentiment = check_market_risk(df)
    if not is_safe:
        print("\n⚠️ 市场风险较高，建议今日观望！")
        print("   (指数大跌 或 赚钱效应低于20%)")
        # 仍然继续扫描，但给出警告
    
    # 加载 RPS 数据
    rps_df = load_latest_rps()
    has_rps = rps_df is not None
    if not has_rps:
        print("⚠️ 未找到 RPS 数据，请先运行 update_rps.py")
    
    # 实时行情已在上面获取
    
    # 第一轮筛选
    print("\n🔍 第一轮: 基础条件过滤...")
    pool = filter_by_basic_conditions(df)
    print(f"   命中: {len(pool)} 只")
    
    if len(pool) == 0:
        print("\n❌ 今日无符合基础条件的标的")
        return []
    
    # 第二轮筛选：并发获取历史数据
    print("\n🔍 第二轮: MA5 + RPS 筛选...")
    
    candidate_codes = pool['代码'].tolist()
    print(f"   正在并发获取 {len(candidate_codes)} 只股票的历史数据...")
    
    # 并发获取历史数据
    history_data = {}
    with ThreadPoolExecutor(max_workers=CONCURRENT.get('max_workers', 10)) as executor:
        futures = {
            executor.submit(get_stock_history, code, 15): code 
            for code in candidate_codes
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                hist = future.result()
                if hist is not None and len(hist) >= 10:
                    history_data[code] = hist
            except:
                pass
    
    print(f"   成功获取 {len(history_data)} 只")
    
    # 在内存中处理信号（非常快）
    signals = []
    
    # 获取今天的日期字符串（用于日期安全检查）
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    
    for _, row in pool.iterrows():
        code = row['代码']
        hist = history_data.get(code)
        
        if hist is None:
            continue
        
        try:
            # ---【日期安全检查】防止"未来函数"---
            # 确保历史数据不包含今天
            hist = hist.copy()
            hist['日期_str'] = pd.to_datetime(hist['日期']).dt.strftime('%Y-%m-%d')
            if hist.iloc[-1]['日期_str'] == today_str:
                # 如果最后一行是今天，切掉它！
                hist = hist.iloc[:-1]
            
            # 确保切完之后数据还够
            if len(hist) < 10:
                continue
            
            # 准备数据 (现在这里的 closes 绝对是截止到昨天的)
            closes = hist['收盘'].tolist()
            
            # 昨天和前天的数据
            prev_row = hist.iloc[-1]  # 最后一行是昨天
            prev_prev_close = hist.iloc[-2]['收盘'] if len(hist) >= 2 else prev_row['收盘']
            prev_pct = (prev_row['收盘'] - prev_prev_close) / prev_prev_close * 100
            
            # 获取 RPS
            stock_rps = 50
            if has_rps:
                rps_data = rps_df[rps_df['symbol'] == code]
                if not rps_data.empty:
                    stock_rps = rps_data.iloc[0]['rps']
            
            # 生成信号 - 传入完整的收盘价列表（不再切片）
            signal = generate_signal(
                code=code,
                name=row['名称'],
                current_price=row['最新价'],
                pct_change=row['涨跌幅'],
                turnover=row['换手率'],
                volume_ratio=row['量比'],
                amplitude=row['振幅'],
                hist_closes=closes,  # 修复：直接传完整列表
                prev_close=prev_row['收盘'],
                prev_open=prev_row['开盘'],
                prev_pct=prev_pct,
                rps=stock_rps
            )
            
            if signal:
                signals.append(signal)
                
        except Exception as e:
            continue
    
    # 输出结果
    if signals:
        result_df = pd.DataFrame(signals)
        result_df = result_df.sort_values(by='RPS', ascending=False)
        
        print("\n" + "=" * 70)
        print("🏆 选股结果")
        print("=" * 70)
        
        # 分类显示
        for category in ["⭐ 趋势核心", "🔥 潜力股", "📊 稳健标的"]:
            subset = result_df[result_df['分类'] == category]
            if not subset.empty:
                print(f"\n【{category}】")
                cols = ['代码', '名称', '现价', '涨幅%', 'RPS', '连阳']
                if category == "⭐ 趋势核心":
                    cols.append('建议')
                print(subset[cols].to_string(index=False))
        
        # 保存
        filename = f"选股结果_{datetime.date.today().strftime('%Y%m%d')}.csv"
        filepath = os.path.join(RESULTS_DIR, filename)
        result_df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"\n💾 结果已保存: {filepath}")
        print(f"   共 {len(signals)} 只股票")
        
        return signals
    else:
        print("\n❌ 今日无符合所有条件的标的")
        return []


if __name__ == "__main__":
    signals = run_scan()
    
    # 可选：推送通知
    # from src.notifier import notify_stock_signals
    # if signals:
    #     notify_stock_signals(signals)

#!/usr/bin/env python
"""
交易战绩可视化 Dashboard
使用 Streamlit 运行: streamlit run dashboard.py

功能：
1. 资金曲线图
2. 胜率统计
3. 策略分析
4. 持仓天数分布
"""
import os
import sys
import pandas as pd
import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 数据文件路径
HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "trade_history.csv")

def load_trade_history():
    """加载交易历史"""
    if not os.path.exists(HISTORY_FILE):
        return None
    
    try:
        df = pd.read_csv(HISTORY_FILE)
        df['盈亏%'] = df['盈亏%'].astype(float)
        df['卖出日期'] = pd.to_datetime(df['卖出日期'])
        return df
    except:
        return None


def print_summary(df):
    """打印交易统计摘要"""
    if df is None or len(df) == 0:
        print("📭 暂无交易记录")
        return
    
    print("=" * 70)
    print("📊 交易战绩报告")
    print(f"   统计时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    # 基本统计
    total = len(df)
    wins = len(df[df['盈亏%'] > 0])
    losses = len(df[df['盈亏%'] < 0])
    flat = len(df[df['盈亏%'] == 0])
    
    win_rate = wins / total * 100 if total > 0 else 0
    avg_pnl = df['盈亏%'].mean()
    total_pnl = df['盈亏%'].sum()
    
    print(f"\n📈 总体统计:")
    print(f"   总交易笔数: {total}")
    print(f"   盈利/亏损/平: {wins}/{losses}/{flat}")
    print(f"   胜率: {win_rate:.1f}%")
    print(f"   平均收益: {avg_pnl:.2f}%")
    print(f"   累计收益: {total_pnl:.2f}%")
    
    # 盈亏详情
    if wins > 0:
        avg_win = df[df['盈亏%'] > 0]['盈亏%'].mean()
        max_win = df['盈亏%'].max()
        print(f"\n💰 盈利交易:")
        print(f"   平均盈利: +{avg_win:.2f}%")
        print(f"   最大单笔: +{max_win:.2f}%")
    
    if losses > 0:
        avg_loss = df[df['盈亏%'] < 0]['盈亏%'].mean()
        max_loss = df['盈亏%'].min()
        print(f"\n📉 亏损交易:")
        print(f"   平均亏损: {avg_loss:.2f}%")
        print(f"   最大单笔: {max_loss:.2f}%")
    
    # 盈亏比
    if losses > 0 and wins > 0:
        avg_win = df[df['盈亏%'] > 0]['盈亏%'].mean()
        avg_loss = abs(df[df['盈亏%'] < 0]['盈亏%'].mean())
        ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')
        print(f"\n⚖️ 盈亏比: {ratio:.2f}")
    
    # 按策略分析
    print(f"\n🏷️ 按策略分析:")
    print("-" * 50)
    for strategy in df['策略'].unique():
        strat_df = df[df['策略'] == strategy]
        s_total = len(strat_df)
        s_wins = len(strat_df[strat_df['盈亏%'] > 0])
        s_rate = s_wins / s_total * 100 if s_total > 0 else 0
        s_avg = strat_df['盈亏%'].mean()
        print(f"   {strategy}: {s_total}笔, 胜率{s_rate:.0f}%, 平均{s_avg:+.2f}%")
    
    # 持仓天数分析
    if '持仓天数' in df.columns:
        avg_days = df['持仓天数'].mean()
        print(f"\n📅 平均持仓天数: {avg_days:.1f} 天")
        if avg_days > 5:
            print("   ⚠️ 持仓时间偏长，注意是否违背超短线初衷")
    
    # 最近交易
    print(f"\n📋 最近5笔交易:")
    print("-" * 70)
    recent = df.tail(5)[['代码', '名称', '买入价', '卖出价', '盈亏%', '策略', '卖出日期']]
    for _, row in recent.iterrows():
        pnl = row['盈亏%']
        emoji = "💰" if pnl > 0 else "📉" if pnl < 0 else "➖"
        print(f"   {emoji} {row['代码']} {row['名称']}: {pnl:+.2f}% [{row['策略']}]")
    
    print("=" * 70)


def run_streamlit_dashboard():
    """运行 Streamlit 可视化界面"""
    try:
        import streamlit as st
        import plotly.express as px
        import plotly.graph_objects as go
    except ImportError:
        print("❌ 需要安装 streamlit 和 plotly:")
        print("   pip install streamlit plotly")
        return
    
    st.set_page_config(page_title="AlphaHunter 战绩", layout="wide")
    st.title("📈 AlphaHunter 交易战绩")
    
    df = load_trade_history()
    
    if df is None or len(df) == 0:
        st.warning("暂无交易记录，请先完成一些交易后再查看。")
        return
    
    # 顶部指标
    col1, col2, col3, col4 = st.columns(4)
    
    total = len(df)
    wins = len(df[df['盈亏%'] > 0])
    win_rate = wins / total * 100
    avg_pnl = df['盈亏%'].mean()
    total_pnl = df['盈亏%'].sum()
    
    col1.metric("总交易笔数", total)
    col2.metric("胜率", f"{win_rate:.1f}%")
    col3.metric("平均收益", f"{avg_pnl:+.2f}%")
    col4.metric("累计收益", f"{total_pnl:+.2f}%")
    
    # 资金曲线
    st.subheader("📈 资金曲线")
    df_sorted = df.sort_values('卖出日期')
    df_sorted['累计收益'] = df_sorted['盈亏%'].cumsum()
    
    fig = px.line(df_sorted, x='卖出日期', y='累计收益', 
                  title='累计收益曲线 (%)')
    fig.update_traces(line_color='#00d26a')
    st.plotly_chart(fig, use_container_width=True)
    
    # 策略分析
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏷️ 策略分析")
        strategy_stats = df.groupby('策略').agg({
            '盈亏%': ['count', 'mean', 'sum']
        }).round(2)
        strategy_stats.columns = ['交易笔数', '平均收益%', '累计收益%']
        st.dataframe(strategy_stats)
    
    with col2:
        st.subheader("📊 盈亏分布")
        fig = px.histogram(df, x='盈亏%', nbins=20, 
                          title='盈亏分布图')
        fig.add_vline(x=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)
    
    # 最近交易记录
    st.subheader("📋 交易记录")
    st.dataframe(df.sort_values('卖出日期', ascending=False))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='交易战绩可视化')
    parser.add_argument('--web', action='store_true', help='启动 Streamlit Web 界面')
    
    args = parser.parse_args()
    
    if args.web:
        print("正在启动 Streamlit 界面...")
        print("如果没有自动打开浏览器，请访问 http://localhost:8501")
        os.system(f"streamlit run {__file__}")
    else:
        # 命令行模式
        df = load_trade_history()
        print_summary(df)

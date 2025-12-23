#!/usr/bin/env python
"""
交易战绩可视化 Dashboard 任务
"""
import os
import sys
import pandas as pd
import datetime

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.utils import logger

# 数据文件路径
HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "trade_history.csv")

def load_trade_history():
    """加载并清洗交易历史"""
    if not os.path.exists(HISTORY_FILE):
        return None
    
    try:
        df = pd.read_csv(HISTORY_FILE)
        df['盈亏%'] = pd.to_numeric(df['盈亏%'], errors='coerce').fillna(0)
        df['卖出日期'] = pd.to_datetime(df['卖出日期'])
        return df
    except Exception as e:
        logger.error(f"⚠️ 加载历史记录失败: {e}")
        return None


def print_summary(df):
    """在终端打印文字统计报告"""
    if df is None or len(df) == 0:
        logger.info("📭 暂无交易记录")
        return
    
    logger.info("=" * 70)
    logger.info("📊 交易战绩总结报告")
    logger.info(f"   统计时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 70)
    
    # 基本指标提取
    total = len(df)
    wins = len(df[df['盈亏%'] > 0])
    losses = len(df[df['盈亏%'] < 0])
    flat = len(df[df['盈亏%'] == 0])
    
    win_rate = (wins / total * 100) if total > 0 else 0
    avg_pnl = df['盈亏%'].mean()
    total_pnl = df['盈亏%'].sum()
    
    logger.info(f"\n📈 核心指标:")
    logger.info(f"   总成交笔数: {total}")
    logger.info(f"   胜率状况:   {win_rate:.1f}% (胜/负/平: {wins}/{losses}/{flat})")
    logger.info(f"   平均利润:   {avg_pnl:.2f}%")
    logger.info(f"   累计总收益: {total_pnl:.2f}%")
    
    # 极端值分析
    if not df.empty:
        logger.info(f"\n💰 利润详情:")
        logger.info(f"   最大盈利: +{df['盈亏%'].max():.2f}%")
        logger.info(f"   最大亏损: {df['盈亏%'].min():.2f}%")
    
    # 策略绩效对比
    if '策略' in df.columns:
        logger.info(f"\n🏷️ 各策略绩效:")
        strategy_stats = df.groupby('策略')['盈亏%'].agg(['count', 'mean', 'sum']).round(2)
        logger.info(strategy_stats.to_string())
    
    # 近期动态
    logger.info(f"\n📋 最近 5 笔成交记录:")
    recent = df.tail(5)
    for _, row in recent.iterrows():
        pnl = row['盈亏%']
        icon = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        logger.info(f"   {icon} {row['代码']} {row['名称']}: {pnl:+.2f}% ({row['策略']})")
    
    logger.info("\n" + "=" * 70)


def run_streamlit_app():
    """供 main.py 调用的启动接口"""
    # 获取此文件的绝对路径，以便 streamlit 运行
    this_file = os.path.abspath(__file__)
    logger.info(f"🚀 正在启动 Dashboard (Streamlit)...")
    logger.info(f"   运行文件: {this_file}")
    
    # 执行 streamlit run 命令
    import subprocess
    try:
        # 注意：这里需要确保 streamlit 已安装
        subprocess.run(["streamlit", "run", this_file], check=True)
    except Exception as e:
        logger.error(f"❌ 启动 Streamlit 失败: {e}")


# 以下代码块仅供 streamlit run 调用时执行其内逻辑
# Streamlit 运行时 __name__ 不是 __main__ 时也会执行顶层
try:
    import streamlit as st
    import plotly.express as px
    
    # 如果检测到是在 streamlit 环境下运行
    if 'st' in locals() or 'streamlit' in sys.modules:
        def render_web_ui():
            st.set_page_config(page_title="AlphaHunter 战绩看板", layout="wide")
            st.title("📈 AlphaHunter 交易战绩 (Web 版)")
            
            # 重新定位根目录（由于 st 环境可能重置了路径）
            sys.path.insert(0, PROJECT_ROOT)
            
            data = load_trade_history()
            if data is None or data.empty:
                st.warning("📭 目前还没有采集到任何交易历史数据。")
                return

            # 指标卡片
            m1, m2, m3, m4 = st.columns(4)
            total = len(data)
            wins = len(data[data['盈亏%'] > 0])
            m1.metric("交易次数", total)
            m2.metric("累计盈亏", f"{data['盈亏%'].sum():.2f}%")
            m3.metric("胜率", f"{wins/total*100:.1f}%")
            m4.metric("平均盈亏", f"{data['盈亏%'].mean():.2f}%")

            # 收益曲线
            st.subheader("收益增长曲线")
            data_sorted = data.sort_values('卖出日期')
            data_sorted['cumulative'] = data_sorted['盈亏%'].cumsum()
            fig = px.line(data_sorted, x='卖出日期', y='cumulative', title="累计百分比收益", labels={'cumulative': '累计收益 %'})
            st.plotly_chart(fig, use_container_width=True)

            # 底部记录表
            st.subheader("最近成交明细")
            st.dataframe(data.sort_values('卖出日期', ascending=False), use_container_width=True)

        # 仅当确定在 streamlit 的运行上下文时执行渲染
        # 注意：streamlit run 时入口脚本会执行两遍，需要小心处理
        if st._is_running_with_streamlit:
            render_web_ui()

except ImportError:
    pass

if __name__ == "__main__":
    # 直接运行此脚本时显示终端总结
    data = load_trade_history()
    print_summary(data)

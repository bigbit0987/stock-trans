#!/usr/bin/env python
"""
尾盘选股扫描任务
建议在 14:35 - 14:50 运行
"""
import os
import sys
import datetime
import pandas as pd

# 添加项目根目录到路径
# 路径层级: src/tasks/scanner.py -> src/tasks/ -> src/ -> stock_trans/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import STRATEGY, RESULTS_DIR, CONCURRENT, RISK_CONTROL
from src.data_loader import get_realtime_quotes, load_latest_rps, get_stock_history
from src.strategy import filter_by_basic_conditions, generate_signal
from src.utils import logger


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
        
        logger.info(f"   上证指数: {sh_pct:+.2f}%")
        logger.info(f"   涨/跌家数: {up_count}/{down_count} (赚钱效应: {sentiment:.0%})")
        
        # 使用配置文件中的阈值
        drop_threshold = RISK_CONTROL.get('market_drop_threshold', -1.5)
        sentiment_threshold = RISK_CONTROL.get('sentiment_threshold', 0.2)
        
        # 判定逻辑: 指数大跌 OR 全场普跌
        is_safe = (sh_pct > drop_threshold) and (sentiment > sentiment_threshold)
        
        return is_safe, sh_pct, sentiment
        
    except Exception as e:
        logger.error(f"   ⚠️ 风控检查出错: {e}")
        logger.warning(f"   ⚠️ 默认返回\"不安全\"，请检查网络")
        return False, 0, 0  # 风控失败时默认不安全！


def run_scan():
    """运行尾盘扫描"""
    logger.info("=" * 60)
    logger.info("🚀 尾盘选股扫描启动")
    logger.info(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 检查是否周末
    weekday = datetime.datetime.today().weekday()
    if weekday >= 5:
        logger.warning("\n⚠️ 警告：今天是周末，A股不开市，数据可能未更新！")
    
    # 获取实时行情 (先获取，用于风控和筛选)
    df = get_realtime_quotes()
    
    # 检查大盘风险 (复用已获取的数据)
    logger.info("\n📊 检查大盘状态...")
    is_safe, sh_pct, sentiment = check_market_risk(df)
    if not is_safe:
        logger.warning("\n⚠️ 市场风险较高，建议今日观望！")
        logger.warning("   (指数大跌 或 赚钱效应低于20%)")
        # 仍然继续扫描，但给出警告
    
    # 加载 RPS 数据
    rps_df = load_latest_rps()
    has_rps = rps_df is not None
    if not has_rps:
        logger.error("⚠️ 未找到 RPS 数据，请先运行 update_rps.py")
    
    # 第一轮筛选: 统计数据筛选 (价格、涨幅、成交量、量比、MA5乖离等)
    logger.info("\n🔍 第一轮筛选: 基础条件筛选中...")
    candidates = filter_by_basic_conditions(df)
    logger.info(f"   符合初选条件: {len(candidates)} 只")
    
    if candidates.empty:
        logger.info("❌ 没有符合条件的标的")
        return
        
    # 第二轮筛选: 并发获取历史数据计算 MA5 趋势和 RPS 评分
    logger.info("\n🔍 第二轮筛选: 计算 MA5 趋势和 RPS 强度...")
    signals = []
    
    # 准备工作
    codes = candidates['代码'].tolist()
    names = candidates['名称'].tolist()
    closes = candidates['最新价'].tolist()
    
    max_workers = CONCURRENT.get('max_workers', 10)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_stock = {
            executor.submit(get_stock_history, code, period='daily'): (code, name, close) 
            for code, name, close in zip(codes, names, closes)
        }
        
        for future in as_completed(future_to_stock):
            code, name, current_close = future_to_stock[future]
            try:
                hist = future.result()
                if hist is not None and len(hist) >= 5:
                    # 计算 RPS (如果存在)
                    rps_score = 0
                    if has_rps:
                        rps_row = rps_df[rps_df['代码'] == code]
                        if not rps_row.empty:
                            rps_score = rps_row.iloc[0]['RPS']
                    
                    # 准备生成信号所需数据
                    # hist 包含历史记录，但不包含今天的最新价，手动合并
                    hist_closes = hist['收盘'].tolist()
                    
                    # 调用通用信号生成函数
                    strategy_result = generate_signal(code, name, current_close, hist_closes, rps_score)
                    
                    if strategy_result:
                        signals.append(strategy_result)
            except Exception as e:
                logger.error(f"   ⚠️ 处理 {code} 出错: {e}")
                
    # 排序和输出结果
    if not signals:
        logger.info("\n❌ 今日未发现推荐买入标的")
        return
        
    # 按 RPS 强度排序
    results_df = pd.DataFrame(signals)
    results_df = results_df.sort_values(by='RPS', ascending=False)
    
    # 保存结果
    today = datetime.datetime.now().strftime('%Y%m%d')
    output_path = os.path.join(RESULTS_DIR, f"选股结果_{today}.csv")
    results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✨ 选股完成！命中 {len(results_df)} 只")
    logger.info(f"📄 结果已保存至: {output_path}")
    logger.info("-" * 60)
    
    # 打印前 5 只（或者全部）
    print_df = results_df.head(10)[['代码', '名称', '最新价', 'RPS', '策略']]
    logger.info(print_df.to_string(index=False))
    logger.info("=" * 60)
    
    # 手机推送提醒
    try:
        from src.notifier import notify_stock_signals
        notify_stock_signals(results_df)
        logger.info("\n📱 信号已推送到手机")
    except Exception as e:
        logger.error(f"   ⚠️ 推送失败: {e}")


if __name__ == "__main__":
    run_scan()

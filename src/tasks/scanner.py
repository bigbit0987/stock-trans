#!/usr/bin/env python
"""
尾盘选股扫描任务
建议在 14:35 - 14:50 运行
"""
import os
import sys
import datetime
import pandas as pd
import glob

# 添加项目根目录到路径
# 路径层级: src/tasks/scanner.py -> src/tasks/ -> src/ -> stock_trans/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import STRATEGY, RESULTS_DIR, CONCURRENT, RISK_CONTROL, RPS_DATA_DIR, CAPITAL
from src.data_loader import get_realtime_quotes, load_latest_rps, get_stock_history, get_cache_stats
from src.strategy import filter_by_basic_conditions, generate_signal
from src.utils import logger


def check_market_risk(realtime_df: pd.DataFrame = None) -> tuple:
    """
    检查大盘风险 (增强版: 指数 + 涨跌家数)
    
    风控逻辑:
    1. 监控上证指数涨跌幅，防止大盘暴跌风险
    2. 计算市场赚钱效应（上涨家数占比），判断市场情绪
    3. 结合指数和市场情绪给出综合风险评级
    
    Args:
        realtime_df: 可选，如果已经获取了实时行情，直接复用，避免重复获取数据
    
    Returns:
        tuple: (是否安全, 上证涨跌幅, 赚钱效应)
            - 是否安全: bool，True表示市场风险可控，可以正常交易
            - 上证涨跌幅: float，上证指数当日涨跌幅百分比
            - 赚钱效应: float，上涨股票家数占比（0-1之间）
    
    风控标准:
        - 指数跌幅超过阈值（默认-1.5%）时视为风险
        - 上涨家数占比低于阈值（默认20%）时视为情绪冰点
        - 任一条件触发都会判定为市场风险较高
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
    """运行尾盘扫描
    
    主要功能:
    1. 检查大盘风险状态
    2. 获取实时行情数据
    3. 多轮筛选符合条件的股票
    4. 计算技术指标和RPS强度
    5. 生成选股信号和交易建议
    
    运行时间建议: 14:35-14:50 (尾盘时段)
    """
    logger.info("=" * 60)
    logger.info("🚀 尾盘选股扫描启动 (多因子增强版 v2.3)")
    logger.info(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 显示缓存状态
    try:
        cache_stats = get_cache_stats()
        logger.info(f"\n📦 缓存状态: 历史数据 {cache_stats['history_cached']} 只, 动量 {cache_stats['momentum_cached']} 只")
    except Exception:
        pass
    
    # 检查是否周末
    weekday = datetime.datetime.today().weekday()
    if weekday >= 5:
        logger.warning("\n⚠️ 警告：今天是周末，A股不开市，数据可能未更新！")
    
    # =========================================
    # 大盘风控检查 (增强版)
    # =========================================
    try:
        from config import MARKET_RISK_CONTROL
        from src.factors import get_market_condition, print_market_condition
        
        if MARKET_RISK_CONTROL.get('enabled', True):
            market_cond = print_market_condition()
            
            # 检查是否应该停止交易
            is_risky = not market_cond['safe']
            
            # 获取风控配置
            risk_config = MARKET_RISK_CONTROL
            sleep_mode = risk_config.get('sleep_mode', {})
            
            if is_risky and risk_config.get('enabled', True):
                # 检查是否触发休眠模式
                if sleep_mode.get('enabled', False):
                    trigger = sleep_mode.get('trigger', 'below_ma20')
                    should_sleep = False
                    reason = ""
                    
                    if trigger == 'below_ma20' and not market_cond.get('above_ma20', True):
                        should_sleep = True
                        reason = "大盘跌破20日均线 (空头趋势)"
                    elif market_cond.get('index_change', 0) < risk_config.get('index_drop_threshold', -2.0):
                        should_sleep = True
                        reason = f"大盘暴跌 ({market_cond.get('index_change'):.2f}%)"
                    
                    if should_sleep:
                        msg = f"🛑 触发休眠模式: {reason}"
                        logger.warning(f"\n{msg}")
                        
                        if sleep_mode.get('notify_on_sleep', True):
                             from src.notifier import notify_all
                             notify_all("系统进入休眠模式 💤", f"触发条件: {reason}\n\n建议: 市场风险较高，系统已暂停选股，建议空仓观望。")
                        
                        return []

                # 旧版兼容逻辑
                action = risk_config.get('below_ma20_action', 'warn')
                if action == 'stop':
                    logger.warning("\n🛑 大盘风控触发，今日停止选股！")
                    return []
                elif action == 'warn':
                    logger.warning("\n⚠️ 大盘风控警告，建议谨慎操作！")
    except Exception as e:
        logger.warning(f"大盘风控检查失败: {e}")
    # =========================================
    
    # 获取实时行情 (先获取，用于风控和筛选)
    df = get_realtime_quotes()
    
    # 检查大盘风险 (复用已获取的数据) - 简化版检查
    logger.info("\n📊 检查市场情绪...")
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
    else:
        # 检查数据是否过期 (Data Integrity)
        list_of_files = glob.glob(os.path.join(RPS_DATA_DIR, 'rps_rank_*.csv'))
        if list_of_files:
            latest_file = max(list_of_files, key=os.path.getctime)
            file_date_str = os.path.basename(latest_file).split('_')[-1].replace('.csv', '')
            today_str = datetime.datetime.now().strftime('%Y%m%d')
            
            if file_date_str != today_str:
                logger.warning("!" * 60)
                logger.warning(f"⚠️ 警告: 使用的 RPS 数据过期！({file_date_str})")
                logger.warning("   建议先运行: python main.py update")
                logger.warning("!" * 60)
    
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
        # 准备数据字典，方便线程中使用
        stock_data_map = {}
        for _, row in candidates.iterrows():
            stock_data_map[row['代码']] = {
                'name': row['名称'],
                'current_close': row['最新价'],
                'pct_change': row['涨跌幅'],
                'turnover': row['换手率'],
                'volume_ratio': row['量比'],
                'amplitude': row['振幅']
            }

        future_to_stock = {
            executor.submit(
                lambda c: (get_stock_history(c), get_tail_volume_ratio(c)), 
                code
            ): code 
            for code in stock_data_map.keys()
        }
        
        for future in as_completed(future_to_stock):
            code = future_to_stock[future]
            try:
                hist, tail_vol_ratio = future.result()
                
                # 更新 stock_data_map 加入尾盘数据
                stock_data_map[code]['tail_vol_ratio'] = tail_vol_ratio
                
                # ---【防止未来函数】---
                # 确保 hist 中不包含今天正在交易的 K 线数据
                if hist is not None and not hist.empty:
                    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
                    # 统一日期格式进行对比
                    hist['日期_str'] = pd.to_datetime(hist['日期']).dt.strftime('%Y-%m-%d')
                    if hist.iloc[-1]['日期_str'] == today_str:
                        hist = hist.iloc[:-1] # 切除今天，只保留到昨天的纯净历史数据
                
                if hist is not None and len(hist) >= 5:
                    data = stock_data_map[code]
                    
                    # 计算 RPS (如果存在)
                    rps_score = 0
                    sector_rps = 0
                    rps_change = 0
                    sector_name = ''  # 板块名称，用于板块滤网
                    
                    if has_rps:
                        rps_row = rps_df[rps_df['代码'] == code]
                        if not rps_row.empty:
                            row_data = rps_row.iloc[0]
                            # 使用 pd.notna 检查空值，确保不会传递 NaN
                            rps_val = row_data.get('RPS', 0)
                            rps_score = rps_val if pd.notna(rps_val) else 0
                            sector_rps_val = row_data.get('板块RPS', 0)
                            sector_rps = sector_rps_val if pd.notna(sector_rps_val) else 0
                            rps_change_val = row_data.get('RPS变动', 0)
                            rps_change = rps_change_val if pd.notna(rps_change_val) else 0
                            sector_val = row_data.get('板块', '')
                            sector_name = sector_val if pd.notna(sector_val) else ''  # 获取板块名称
                            
                            # v2.5.0: 获取 RPS20 (短周期动量)
                            rps20_val = row_data.get('RPS20', 0)
                            rps20_score = rps20_val if pd.notna(rps20_val) else 0
                    
                    # 提取前一天数据 (hist 的最后一行通常是前一个交易日)
                    prev_day = hist.iloc[-1]
                    prev_close = prev_day['收盘']
                    prev_open = prev_day['开盘']
                    prev_pct = prev_day['涨跌幅']
                    
                    hist_closes = hist['收盘'].tolist()
                    
                    # 获取历史成交量 (v2.4 支持)
                    hist_volumes = hist['成交量'].tolist() if '成交量' in hist.columns else []
                    
                    # 调用通用信号生成函数 (v2.5.0: 传入 rps20 和 tail_vol_ratio)
                    strategy_result = generate_signal(
                        code, data['name'], data['current_close'], 
                        data['pct_change'], data['turnover'], data['volume_ratio'], data['amplitude'],
                        hist_closes, prev_close, prev_open, prev_pct, rps_score,
                        sector_rps, rps_change, rps20_score, hist_volumes, 
                        tail_vol_ratio=data.get('tail_vol_ratio', 0)
                    )
                    
                    if strategy_result:
                        # 添加板块名称（用于板块滤网功能）
                        strategy_result['板块'] = sector_name
                        
                        # ---【计算建议仓位】---
                        target_amt = CAPITAL.get('target_amount_per_stock', 0)
                        if target_amt > 0:
                            # 为每只股票计算建议手数 (向下取整到 100 股)
                            current_price = strategy_result['现价']
                            suggested_vol = int(target_amt / current_price / 100) * 100
                            strategy_result['建议买入'] = f"{suggested_vol} 股"
                        
                        signals.append(strategy_result)
            except Exception as e:
                logger.error(f"   ⚠️ 处理 {code} 出错: {e}")
                
    # 排序和输出结果
    if not signals:
        logger.info("\n❌ 今日未发现推荐买入标的")
        return []
    
    # =========================================
    # 多因子评分 (v2.3 新增)
    # =========================================
    try:
        from config import MULTI_FACTOR
        from src.factors import batch_calculate_scores, get_hot_sectors
        
        if MULTI_FACTOR.get('enabled', True):
            logger.info("\n📊 第三轮筛选: 多因子综合评分...")
            
            # 显示热门板块
            hot_sectors = get_hot_sectors(5)
            if hot_sectors:
                logger.info(f"   🔥 今日热门板块: {', '.join([s['name'] for s in hot_sectors])}")
            
            # 计算多因子评分
            scored_signals = batch_calculate_scores(signals)
            
            # 按综合得分过滤和排序
            min_score = MULTI_FACTOR.get('min_total_score', 60)
            scored_signals = [s for s in scored_signals if s.get('total_score', 0) >= min_score]
            
            if scored_signals:
                signals = scored_signals
                logger.info(f"   ✅ 多因子筛选后: {len(signals)} 只 (综合评分 ≥ {min_score})")
            else:
                logger.warning(f"   ⚠️ 多因子筛选后无符合条件股票 (最低要求: {min_score}分)")
    except Exception as e:
        logger.warning(f"多因子评分失败，使用原始排序: {e}")
    
    # =========================================
    # 板块滤网 (v2.3.1 新增)
    # =========================================
    try:
        from config import SECTOR_FILTER
        from src.indicators import is_sector_strong
        from src.factors import get_hot_sectors, get_stock_sector
        
        if SECTOR_FILTER.get('enabled', True):
            top_pct = SECTOR_FILTER.get('top_pct', 0.33)
            all_sectors = get_hot_sectors(100)  # 获取所有板块排名
            
            before_count = len(signals)
            filtered_signals = []
            
            for s in signals:
                code = s.get('代码', '')
                # 优先使用已有的板块信息（来自batch_calculate_scores或RPS数据）
                # 避免逐个调用get_stock_sector导致性能问题
                sector = s.get('板块', '') or s.get('sector', '')
                if not sector:
                    # 只有在没有板块信息时才尝试获取（但这应该很少发生）
                    sector = get_stock_sector(code)
                
                if sector and is_sector_strong(sector, all_sectors, top_pct):
                    filtered_signals.append(s)
                elif s.get('grade') == 'A':
                    # A级股票不受板块限制
                    filtered_signals.append(s)
                elif not sector:
                    # 无法获取板块信息的股票也放行（不因数据问题错过机会）
                    filtered_signals.append(s)
            
            if filtered_signals:
                signals = filtered_signals
                logger.info(f"   🔍 板块滤网: 保留 {len(signals)} 只 (板块排名前{int(top_pct*100)}%)")
    except Exception as e:
        logger.warning(f"板块滤网失败: {e}")
    
    # =========================================
    # 凯利公式仓位计算 (v2.3.1 新增)
    # =========================================
    try:
        from config import KELLY_POSITION
        from src.indicators import calculate_dynamic_position_size
        
        if KELLY_POSITION.get('enabled', True):
            base_amount = KELLY_POSITION.get('base_amount', 50000)
            kelly_result = calculate_dynamic_position_size(base_amount)
            
            logger.info(f"\n💰 凯利公式仓位建议:")
            logger.info(f"   历史胜率: {kelly_result['win_rate']*100:.1f}%")
            logger.info(f"   建议金额: {kelly_result['suggested_amount']:.0f} 元 ({kelly_result['adjustment']})")
            
            # 为每只股票更新建议买入金额
            for s in signals:
                current_price = s.get('现价', 0)
                if current_price > 0:
                    suggested_vol = int(kelly_result['suggested_amount'] / current_price / 100) * 100
                    s['建议买入'] = f"{suggested_vol} 股"
                    s['建议金额'] = kelly_result['suggested_amount']
    except Exception as e:
        logger.warning(f"凯利公式计算失败: {e}")
    # =========================================
        
    # 按综合得分或RPS排序
    results_df = pd.DataFrame(signals)
    if 'total_score' in results_df.columns:
        results_df = results_df.sort_values(by='total_score', ascending=False)
    else:
        results_df = results_df.sort_values(by='RPS', ascending=False)
    
    # 保存结果
    today = datetime.datetime.now().strftime('%Y%m%d')
    output_path = os.path.join(RESULTS_DIR, f"选股结果_{today}.csv")
    results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✨ 选股完成！命中 {len(results_df)} 只")
    logger.info(f"📄 结果已保存至: {output_path}")
    logger.info("-" * 60)
    
    # 打印结果 (根据是否有多因子评分选择显示列)
    if 'total_score' in results_df.columns:
        cols = ['代码', '名称', '现价', 'total_score', 'grade', '分类']
        results_df = results_df.rename(columns={'total_score': '综合评分', 'grade': '评级'})
        cols = ['代码', '名称', '现价', '综合评分', '评级', '分类']
    else:
        cols = ['代码', '名称', '现价', 'RPS', '分类']
    
    if '建议买入' in results_df.columns:
        cols.append('建议买入')
    
    available_cols = [c for c in cols if c in results_df.columns]
    print_df = results_df.head(10)[available_cols]
    logger.info(print_df.to_string(index=False))
    logger.info("=" * 60)
    
    # =========================================
    # 板块效应分析 (v2.4 新增)
    # =========================================
    try:
        from src.factors import print_sector_cluster_report
        print_sector_cluster_report(signals)
    except Exception as e:
        logger.warning(f"板块效应分析失败: {e}")
    
    # 自动记录推荐用于效果追踪
    try:
        from src.tasks.performance_tracker import record_daily_recommendations
        record_daily_recommendations(signals)
    except Exception as e:
        logger.warning(f"记录推荐失败: {e}")
    
    # 自动加入虚拟持仓进行策略验证
    try:
        from src.tasks.virtual_tracker import add_recommendations_to_virtual
        add_recommendations_to_virtual(signals)
    except Exception as e:
        logger.warning(f"加入虚拟持仓失败: {e}")
    
    # 返回结果供调用方(如 main.py)处理通知逻辑
    return signals


if __name__ == "__main__":
    run_scan()

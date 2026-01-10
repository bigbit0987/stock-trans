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
from src.data_loader import get_realtime_quotes, load_latest_rps, get_stock_history, get_cache_stats, get_tail_volume_ratio
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
        
        up_count = len(market_df[market_df['pct_change'] > 0])
        down_count = len(market_df[market_df['pct_change'] < 0])
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
    position_multiplier = 1.0  # v2.5.1: 仓位乘数，用于市场宽度渐进式风控
    rps_min_dynamic = STRATEGY.get('rps_min', 40)  # v2.5.2: 动态 RPS 阈值
    check_turnover_spike = False  # v2.5.2: 过热期换手率突变检测标记
    breadth_pct = 10  # v2.5.2: 市场宽度百分比，默认 10%（稍后可能被覆盖）
    
    try:
        from config import MARKET_RISK_CONTROL
        from src.factors import get_market_condition, print_market_condition
        
        if MARKET_RISK_CONTROL.get('enabled', True):
            market_cond = print_market_condition()
            
            # =========================================
            # v2.5.2: Market Breadth 渐进式风控（增强版）
            # 根据市场宽度动态调整操作策略和筛选标准
            # =========================================
            breadth = market_cond.get('market_breadth', {})
            breadth_pct = breadth.get('breadth_pct', 10)  # 默认 10%
            
            # 获取自适应配置
            adaptive_config = MARKET_RISK_CONTROL.get('market_breadth_adaptive', {})
            
            if breadth_pct < 4:
                # 极弱市场：休眠模式
                logger.warning(f"\n🛑 市场宽度预警: 仅 {breadth_pct}% 创新高 (极弱)")
                logger.warning("   触发休眠模式，今日停止选股！")
                
                from src.notifier import notify_all
                notify_all("系统进入休眠模式 💤", 
                          f"触发条件: 市场宽度仅 {breadth_pct}%（创20日新高家数占比极低）\n\n"
                          "分析: 杀强势股行情，即使指数护盘，个股也会普跌。\n"
                          "建议: 空仓观望，等待市场情绪回暖。")
                return []
            elif breadth_pct < adaptive_config.get('cold_market', {}).get('threshold', 8):
                # v2.5.2: 冰点期 - 只做最强核心标的
                cold_config = adaptive_config.get('cold_market', {})
                position_multiplier = cold_config.get('position_multiplier', 0.5)
                rps_min_dynamic = cold_config.get('rps_min_override', 70)
                
                logger.warning(f"\n⚠️ 市场宽度偏弱: {breadth_pct}% 创新高 (冰点期)")
                logger.warning(f"   渐进式风控: 单笔金额 ×{position_multiplier}, RPS 阈值提高至 {rps_min_dynamic}")
            elif breadth_pct > adaptive_config.get('hot_market', {}).get('threshold', 30):
                # v2.5.2: 过热期 - 启用换手率突变检测
                hot_config = adaptive_config.get('hot_market', {})
                if hot_config.get('turnover_spike_check', True):
                    check_turnover_spike = True
                    logger.warning(f"\n🔥 市场过热预警: {breadth_pct}% 创新高")
                    logger.warning(f"   启用换手率突变检测，过滤情绪过热个股")
            else:
                logger.info(f"\n✅ 市场宽度良好: {breadth_pct}% 创新高 ({breadth.get('status', '')})")
            
            # 检查是否应该停止交易 (原有逻辑)
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
    codes = candidates['code'].tolist()
    names = candidates['name'].tolist()
    closes = candidates['close'].tolist()
    
    max_workers = CONCURRENT.get('max_workers', 10)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 准备数据字典，方便线程中使用
        stock_data_map = {}
        for _, row in candidates.iterrows():
            stock_data_map[row['code']] = {
                'name': row['name'],
                'current_close': row['close'],
                'pct_change': row['pct_change'],
                'turnover': row['turnover'],
                'volume_ratio': row['volume_ratio'],
                'amplitude': row['amplitude']
            }

        # v2.5.1: 只获取历史数据，尾盘数据延迟到前10名确认阶段
        # 避免高频调用分钟线 API 导致 IP 封禁
        future_to_stock = {
            executor.submit(get_stock_history, code): code 
            for code in stock_data_map.keys()
        }
        
        for future in as_completed(future_to_stock):
            code = future_to_stock[future]
            try:
                hist = future.result()
                
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
                        rps_row = rps_df[rps_df['code'] == code]
                        if not rps_row.empty:
                            row_data = rps_row.iloc[0]
                            # 使用 pd.notna 检查空值，确保不会传递 NaN
                            rps_val = row_data.get('rps', 0)
                            rps_score = rps_val if pd.notna(rps_val) else 0
                            sector_rps_val = row_data.get('sector_rps', 0)
                            sector_rps = sector_rps_val if pd.notna(sector_rps_val) else 0
                            rps_change_val = row_data.get('rps_change', 0)
                            rps_change = rps_change_val if pd.notna(rps_change_val) else 0
                            sector_val = row_data.get('sector', '')
                            sector_name = sector_val if pd.notna(sector_val) else ''  # 获取板块名称
                            
                            # v2.5.0: 获取 RPS20 (短周期动量)
                            rps20_val = row_data.get('rps20', 0)
                            rps20_score = rps20_val if pd.notna(rps20_val) else 0
                    
                    # v2.5.2: 动态 RPS 阈值过滤
                    if rps_score < rps_min_dynamic:
                        continue  # 冰点期只保留高 RPS 标的
                    
                    # v2.5.2: 过热期换手率突变检测
                    if check_turnover_spike and 'volume' in hist.columns:
                        avg_volume_5d = hist['volume'].tail(5).mean()
                        current_volume = data.get('volume', 0) if 'volume' in data else 0
                        if current_volume > 0 and avg_volume_5d > 0:
                            spike_ratio = MARKET_RISK_CONTROL.get('market_breadth_adaptive', {}).get(
                                'hot_market', {}).get('turnover_spike_ratio', 3.0)
                            if current_volume / avg_volume_5d > spike_ratio:
                                logger.debug(f"   {code} 换手率突变 ({current_volume/avg_volume_5d:.1f}倍)，过热期过滤")
                                continue
                    
                    # 提取前一天数据 (hist 的最后一行通常是前一个交易日)
                    prev_day = hist.iloc[-1]
                    prev_close = prev_day['close']
                    prev_open = prev_day['open']
                    prev_pct = prev_day['pct_change']
                    
                    hist_closes = hist['close'].tolist()
                    
                    # 获取历史成交量
                    hist_volumes = hist['volume'].tolist() if 'volume' in hist.columns else []
                    
                    # 调用通用信号生成函数 (v2.5.1: 尾盘数据延迟获取)
                    strategy_result = generate_signal(
                        code, data['name'], data['current_close'], 
                        data['pct_change'], data['turnover'], data['volume_ratio'], data['amplitude'],
                        hist_closes, prev_close, prev_open, prev_pct, rps_score,
                        sector_rps, rps_change, rps20_score, hist_volumes, 
                        tail_vol_ratio=0  # 延迟到前10名确认阶段再获取
                    )
                    
                    if strategy_result:
                        # 添加板块名称（用于板块滤网功能）
                        strategy_result['sector'] = sector_name
                        
                        # ---【计算建议仓位】---
                        target_amt = CAPITAL.get('target_amount_per_stock', 0)
                        if target_amt > 0:
                            # 为每只股票计算建议手数 (向下取整到 100 股)
                            current_price = strategy_result['close']
                            suggested_vol = int(target_amt / current_price / 100) * 100
                            strategy_result['suggested_volume'] = f"{suggested_vol} 股"
                        
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
            
            # v2.5.1: 市场宽度深度联动
            # breadth > 15%: 仓位加成 1.2x (极强市场)
            # breadth 8-15%: 正常仓位 1.0x
            # breadth 4-8%: 仓位减半 0.5x (已在前面设置)
            if position_multiplier == 1.0 and breadth_pct > 15:
                position_multiplier = 1.2
                logger.info(f"   📈 市场宽度极强 ({breadth_pct}%)，仓位加成 ×1.2")
            
            adjusted_amount = kelly_result['suggested_amount'] * position_multiplier
            for s in signals:
                current_price = s.get('close', 0)
                if current_price > 0:
                    suggested_vol = int(adjusted_amount / current_price / 100) * 100
                    s['suggested_volume'] = f"{suggested_vol} 股"
                    s['suggested_amount'] = adjusted_amount
            
            if position_multiplier < 1.0:
                logger.info(f"   ⚠️ 已应用市场宽度风控: 建议金额 × {position_multiplier:.0%}")
    except Exception as e:
        logger.warning(f"凯利公式计算失败: {e}")
    # =========================================
        
    # 按综合得分或RPS排序
    results_df = pd.DataFrame(signals)
    if 'total_score' in results_df.columns:
        results_df = results_df.sort_values(by='total_score', ascending=False)
    else:
        results_df = results_df.sort_values(by='rps', ascending=False)
    
    # =========================================
    # v2.5.1: 前10名二次确认 - 整合尾盘数据与筹码因子 (ASR)
    # 限制高频 API 调用范围，保障账号安全
    # =========================================
    try:
        top_codes = results_df.head(10)['code'].tolist()
        if top_codes:
            logger.info(f"\n🔬 前10名二次确认: 获取尾盘吸筹数据...")
            
            for code in top_codes:
                try:
                    idx = results_df[results_df['code'] == code].index
                    if len(idx) == 0: continue
                    idx_val = idx[0]
                    
                    # 1. 验证尾盘数据 (意图识别)
                    tail_data = get_tail_volume_ratio(code)
                    tail_ratio = tail_data['ratio']
                    tail_change = tail_data['price_change']
                    
                    if tail_ratio > 15:
                        if tail_change > 0.5:
                            # v2.5.2: 强力吸筹 (放量 + 上涨 > 0.5%)
                            results_df.loc[idx_val, 'remark'] = f"✨尾盘强吸筹({tail_ratio:.0f}%, {tail_change:+.1f}%)"
                            results_df.loc[idx_val, 'total_score'] += min(tail_ratio / 2, 15)  # 加分上限提高
                        elif tail_change > 0:
                            # 意图识别：量增价稳/升 -> 积极吸筹
                            results_df.loc[idx_val, 'remark'] = f"✨尾盘吸筹({tail_ratio:.0f}%, {tail_change:+.1f}%)"
                            results_df.loc[idx_val, 'total_score'] += min(tail_ratio / 2, 10)
                        elif tail_change < -0.5:
                            # v2.5.2: 放量下跌直接剔除 (原 -1.0% 改为 -0.5%)
                            # 策略师建议：次日低开概率极高，即使 Grade A 也不应参与
                            results_df.loc[idx_val, 'remark'] = f"🚫尾盘砸盘({tail_ratio:.0f}%, {tail_change:.1f}%)"
                            results_df.loc[idx_val, '_exclude'] = True  # 标记待剔除
                            logger.warning(f"   ⚠️ {code} 尾盘放量砸盘 ({tail_change:.1f}%)，已剔除")
                        else:
                            # 微跌但放量，给予警告
                            results_df.loc[idx_val, 'remark'] = f"⚠️尾盘异动({tail_ratio:.0f}%, {tail_change:.1f}%)"
                            results_df.loc[idx_val, 'total_score'] -= 3

                    # 2. 验证筹码因子
                    from src.factors import get_shareholder_change_score, calculate_rps_slope, get_rps_history_for_code
                    chip_info = get_shareholder_change_score(code)
                    if chip_info['score'] > 60:
                        existing = results_df.loc[idx_val, 'remark'] if 'remark' in results_df.columns and pd.notna(results_df.loc[idx_val, 'remark']) else ""
                        results_df.loc[idx_val, 'remark'] = f"{existing} {chip_info['label']}".strip()
                        results_df.loc[idx_val, 'total_score'] += 5
                    
                    # 3. v2.5.2: RPS 动量斜率验证
                    rps_history = get_rps_history_for_code(code, days=5)
                    if rps_history:
                        slope_info = calculate_rps_slope(rps_history)
                        adjustment = slope_info['score_adjustment']
                        if adjustment != 0:
                            results_df.loc[idx_val, 'total_score'] += adjustment
                            existing = results_df.loc[idx_val, 'remark'] if 'remark' in results_df.columns and pd.notna(results_df.loc[idx_val, 'remark']) else ""
                            results_df.loc[idx_val, 'remark'] = f"{existing} {slope_info['label']}".strip()
                            if adjustment > 0:
                                logger.debug(f"   {code} {slope_info['label']}, 评分 +{adjustment}")
                            else:
                                logger.debug(f"   {code} {slope_info['label']}, 评分 {adjustment}")
                except Exception as e:
                    logger.debug(f"二次验证失败 {code}: {e}")
            
            # v2.5.1: 剔除尾盘砸盘标的
            if '_exclude' in results_df.columns:
                exclude_count = results_df['_exclude'].sum() if results_df['_exclude'].notna().any() else 0
                if exclude_count > 0:
                    results_df = results_df[results_df['_exclude'] != True]
                    results_df = results_df.drop(columns=['_exclude'], errors='ignore')
                    logger.info(f"   🚫 已剔除 {int(exclude_count)} 只尾盘砸盘标的")
            
            # 重新排序
            if 'total_score' in results_df.columns:
                results_df = results_df.sort_values(by='total_score', ascending=False)
    except Exception as e:
        logger.warning(f"尾盘二次确认失败: {e}")
    
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

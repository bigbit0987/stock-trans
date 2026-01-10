#!/usr/bin/env python
"""
增强型因子库 (Enhanced Factors)
包含:
1. 大盘风控因子
2. 资金流向因子
3. 板块热度因子
4. 估值因子
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from src.utils import logger


# ============================================
# 1. 大盘风控因子
# ============================================

def get_market_condition() -> Dict:
    """
    获取大盘状态，判断是否适合交易
    
    Returns:
        {
            'safe': bool,           # 是否安全
            'index_price': float,   # 上证指数
            'index_change': float,  # 涨跌幅
            'ma5': float,          # 5日均线
            'ma10': float,         # 10日均线
            'ma20': float,         # 20日均线
            'above_ma20': bool,    # 是否在20日均线之上
            'trend': str,          # 趋势判断
            'suggestion': str,     # 操作建议
        }
    """
    try:
        # 获取上证指数实时数据
        index_df = ak.stock_zh_index_spot_em()
        sh_idx = index_df[index_df['代码'] == '000001']
        
        if sh_idx.empty:
            return {'safe': False, 'trend': '数据获取失败', 'suggestion': '暂停交易'}
        
        current_price = sh_idx.iloc[0]['最新价']
        pct_change = sh_idx.iloc[0]['涨跌幅']
        
        # 获取上证指数历史数据计算均线
        hist = ak.index_zh_a_hist(symbol="000001", period="daily", start_date=(datetime.now() - timedelta(days=60)).strftime('%Y%m%d'))
        
        if hist is None or len(hist) < 20:
            return {'safe': False, 'trend': '历史数据不足', 'suggestion': '暂停交易'}
        
        closes = hist['收盘'].tolist()
        
        # 计算均线
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        
        # 判断趋势
        above_ma5 = current_price > ma5
        above_ma10 = current_price > ma10
        above_ma20 = current_price > ma20
        
        # 综合判断
        if above_ma20 and above_ma10:
            trend = "上升趋势"
            safe = True
            suggestion = "正常交易"
        elif above_ma20 and not above_ma10:
            trend = "震荡偏强"
            safe = True
            suggestion = "谨慎交易，减少仓位"
        elif not above_ma20 and above_ma10:
            trend = "反弹中"
            safe = True
            suggestion = "短线可做，注意风险"
        else:
            trend = "下降趋势"
            safe = False
            suggestion = "建议观望，不宜追高"
        
        # 如果当日大跌，额外警告
        if pct_change < -2:
            safe = False
            suggestion = "大盘急跌，暂停交易！"
        
        return {
            'safe': safe,
            'index_price': current_price,
            'index_change': pct_change,
            'ma5': round(ma5, 2),
            'ma10': round(ma10, 2),
            'ma20': round(ma20, 2),
            'above_ma5': above_ma5,
            'above_ma10': above_ma10,
            'above_ma20': above_ma20,
            'trend': trend,
            'suggestion': suggestion,
            'market_breadth': calculate_market_breadth() # v2.5.0: 增加市场宽度
        }
    except Exception as e:
        logger.error(f"获取大盘状态失败: {e}")
        return {'safe': False, 'trend': f'错误: {e}', 'suggestion': '暂停交易'}


def calculate_market_breadth() -> Dict:
    """
    计算市场宽度 (v2.5.0)
    基于 RPS 动量数据中的 '20日新高' 标志
    
    Returns:
        {
            'all_count': int,       # 总样本数
            'high_20_count': int,   # 创20日新高家数
            'breadth_pct': float,   # 占比
            'status': str           # 强弱描述
        }
    """
    try:
        import glob
        from config.settings import RPS_DATA_DIR
        
        # 寻找最新的 RPS 文件
        list_of_files = glob.glob(os.path.join(RPS_DATA_DIR, 'rps_rank_*.csv'))
        if not list_of_files:
            return {'all_count': 0, 'high_20_count': 0, 'breadth_pct': 0, 'status': '未知'}
            
        latest_file = max(list_of_files, key=os.path.getctime)
        df = pd.read_csv(latest_file)
        
        if '20日新高' not in df.columns:
            return {'all_count': len(df), 'high_20_count': 0, 'breadth_pct': 0, 'status': '数据不足'}
            
        # 稳健的布尔判定：支持 0/1, True/False, "True"/"False"
        high_20_count = df['20日新高'].map(lambda x: str(x).lower() == 'true' or x is True or x == 1).sum()
        total = len(df)
        pct = round(high_20_count / total * 100, 2) if total > 0 else 0
        
        if pct > 15:
            status = "极强"
        elif pct > 8:
            status = "良好"
        elif pct > 4:
            status = "一般"
        else:
            status = "较弱"
            
        return {
            'all_count': total,
            'high_20_count': int(high_20_count),
            'breadth_pct': pct,
            'status': status
        }
    except Exception as e:
        logger.debug(f"计算市场宽度失败: {e}")
        return {'all_count': 0, 'high_20_count': 0, 'breadth_pct': 0, 'status': f'错误: {e}'}


def print_market_condition():
    """打印大盘状态"""
    cond = get_market_condition()
    
    logger.info("=" * 60)
    logger.info("📈 大盘风控检查")
    logger.info("=" * 60)
    
    if 'index_price' in cond:
        logger.info(f"   上证指数: {cond['index_price']:.2f} ({cond['index_change']:+.2f}%)")
        logger.info(f"   均线状态: MA5={cond['ma5']} | MA10={cond['ma10']} | MA20={cond['ma20']}")
        logger.info(f"   趋势判断: {cond['trend']}")
    
    if cond['safe']:
        logger.info(f"   ✅ {cond['suggestion']}")
    else:
        logger.info(f"   ⚠️ {cond['suggestion']}")
        
    # v2.5.0: 打印市场宽度
    breadth = cond.get('market_breadth', {})
    if breadth and breadth['all_count'] > 0:
        logger.info(f"   📊 市场宽度: {breadth['breadth_pct']}% ({breadth['high_20_count']}只创新高) | 状态: {breadth['status']}")
    
    logger.info("=" * 60)
    return cond


# ============================================
# 2. 资金流向因子
# ============================================

def get_money_flow_rank(top_n: int = 100) -> pd.DataFrame:
    """
    获取主力资金流入排行
    
    Returns:
        DataFrame with columns: code, name, main_inflow, main_inflow_pct
    """
    try:
        # 获取个股资金流排名
        df = ak.stock_individual_fund_flow_rank(indicator="今日")
        
        if df is None or df.empty:
            logger.warning("资金流向数据获取失败")
            return pd.DataFrame()
        
        # 确保数值列是数值类型 (akshare有时返回字符串)
        df['今日主力净流入-净额'] = pd.to_numeric(df['今日主力净流入-净额'], errors='coerce').fillna(0)
        df['今日主力净流入-净占比'] = pd.to_numeric(df['今日主力净流入-净占比'], errors='coerce').fillna(0)
        
        # 筛选主力净流入为正的股票
        df = df[df['今日主力净流入-净额'] > 0].head(top_n)
        
        # 标准化列名
        result = pd.DataFrame({
            'code': df['代码'].astype(str).str.zfill(6),
            'name': df['名称'],
            'main_inflow': df['今日主力净流入-净额'],
            'main_inflow_pct': df['今日主力净流入-净占比'],
        })
        
        return result
    except Exception as e:
        logger.error(f"获取资金流向失败: {e}")
        return pd.DataFrame()


def get_stock_money_flow(code: str) -> Dict:
    """
    获取单只股票的资金流向
    
    Returns:
        {
            'main_inflow': float,      # 主力净流入(万)
            'main_inflow_pct': float,  # 主力净流入占比(%)
            'retail_inflow': float,    # 散户净流入(万)
            'score': float,            # 资金评分 (0-100)
        }
    """
    try:
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith('6') else "sz")
        
        if df is None or df.empty:
            return {'main_inflow': 0, 'main_inflow_pct': 0, 'retail_inflow': 0, 'score': 50}
        
        # 获取最新一天的数据
        latest = df.iloc[-1]
        
        main_inflow = latest.get('主力净流入-净额', 0)
        # 根据资金流向计算评分
        if main_inflow > 10000:  # 超过1亿
            score = 90
        elif main_inflow > 5000:  # 超过5000万
            score = 80
        elif main_inflow > 1000:  # 超过1000万
            score = 70
        elif main_inflow > 0:
            score = 60
        elif main_inflow > -1000:
            score = 40
        else:
            score = 20
        
        return {
            'main_inflow': main_inflow,
            'main_inflow_pct': latest.get('主力净流入-净占比', 0),
            'retail_inflow': latest.get('小单净流入-净额', 0),
            'score': score,
        }
    except Exception as e:
        logger.debug(f"获取 {code} 资金流向失败: {e}")
        return {'main_inflow': 0, 'main_inflow_pct': 0, 'retail_inflow': 0, 'score': 50}


# ============================================
# 3. 板块热度因子
# ============================================

def get_hot_sectors(top_n: int = 10) -> List[Dict]:
    """
    获取当日热门板块
    
    Returns:
        [{name: 板块名, change: 涨跌幅, rank: 排名}, ...]
    """
    try:
        # 获取行业板块涨幅排行
        df = ak.stock_board_industry_name_em()
        
        if df is None or df.empty:
            return []
        
        # 按涨跌幅排序
        df = df.sort_values('涨跌幅', ascending=False).head(top_n)
        
        result = []
        for i, (_, row) in enumerate(df.iterrows()):
            result.append({
                'name': row['板块名称'],
                'change': row['涨跌幅'],
                'rank': i + 1,
            })
        
        return result
    except Exception as e:
        logger.error(f"获取热门板块失败: {e}")
        return []


# 板块缓存 (避免重复API调用)
_sector_cache = {}
_sector_cache_loaded = False

def load_sector_cache() -> Dict[str, str]:
    """
    批量加载所有股票的板块信息
    通过板块成分股接口反向构建股票->板块映射
    """
    global _sector_cache, _sector_cache_loaded
    
    if _sector_cache_loaded:
        return _sector_cache
    
    try:
        logger.info("   📂 正在加载板块映射缓存...")
        # 获取所有行业板块
        boards = ak.stock_board_industry_name_em()
        if boards is None or boards.empty:
            return {}
        
        # 只处理前30个板块以加快速度
        for _, board in boards.head(30).iterrows():
            sector_name = board['板块名称']
            try:
                # 获取板块成分股
                cons = ak.stock_board_industry_cons_em(symbol=sector_name)
                if cons is not None and not cons.empty:
                    for code in cons['代码'].tolist():
                        code_str = str(code).zfill(6)
                        if code_str not in _sector_cache:
                            _sector_cache[code_str] = sector_name
            except Exception:
                continue
        
        _sector_cache_loaded = True
        logger.info(f"   ✅ 板块缓存加载完成: {len(_sector_cache)} 只股票")
    except Exception as e:
        logger.warning(f"板块缓存加载失败: {e}")
    
    return _sector_cache


def get_stock_sector(code: str) -> Optional[str]:
    """
    获取股票所属行业板块 (优先使用缓存)
    跨平台兼容版本，使用threading实现超时
    """
    global _sector_cache
    
    code_str = str(code).zfill(6)
    
    # 优先使用缓存
    if code_str in _sector_cache:
        return _sector_cache[code_str]
    
    # 缓存未命中，尝试单独查询 (带超时保护，跨平台兼容)
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        
        def _fetch_sector():
            df = ak.stock_individual_info_em(symbol=code_str)
            if df is not None and '所属行业' in df['item'].values:
                return df[df['item'] == '所属行业']['value'].iloc[0]
            return None
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch_sector)
            try:
                sector = future.result(timeout=2)  # 2秒超时
                if sector:
                    _sector_cache[code_str] = sector  # 存入缓存
                    return sector
            except FuturesTimeoutError:
                logger.debug(f"获取 {code_str} 板块信息超时")
            except Exception as e:
                logger.debug(f"获取 {code_str} 板块信息失败: {e}")
    except Exception as e:
        logger.debug(f"板块查询异常 {code_str}: {e}")
    
    return None





def calculate_sector_score(code: str, hot_sectors: List[Dict]) -> float:
    """
    计算股票的板块热度评分
    
    Returns:
        0-100 的评分，热门板块得分高
    """
    try:
        sector = get_stock_sector(code)
        if sector is None:
            return 50  # 默认中等分
        
        for s in hot_sectors:
            if s['name'] in sector or sector in s['name']:
                # 排名越靠前分数越高
                if s['rank'] <= 3:
                    return 95
                elif s['rank'] <= 5:
                    return 85
                elif s['rank'] <= 10:
                    return 75
        
        return 50  # 非热门板块
    except Exception as e:
        logger.debug(f"计算 {code} 板块评分失败: {e}")
        return 50


# ============================================
# 4. 估值因子
# ============================================

def get_stock_valuation(code: str) -> Dict:
    """
    获取股票估值数据
    
    Returns:
        {
            'pe': float,        # 市盈率
            'pb': float,        # 市净率
            'ps': float,        # 市销率
            'market_cap': float,  # 总市值(亿)
            'score': float,     # 估值评分 (0-100)
        }
    """
    try:
        df = ak.stock_zh_a_spot_em()
        stock = df[df['代码'] == code]
        
        if stock.empty:
            return {'pe': 0, 'pb': 0, 'ps': 0, 'market_cap': 0, 'score': 50}
        
        row = stock.iloc[0]
        pe = row.get('市盈率-动态', 0) or 0
        pb = row.get('市净率', 0) or 0
        market_cap = (row.get('总市值', 0) or 0) / 100000000  # 转为亿
        
        # 估值评分逻辑
        score = 50
        
        # PE评分 (低PE加分)
        if 0 < pe < 15:
            score += 20
        elif 15 <= pe < 25:
            score += 10
        elif 25 <= pe < 40:
            score += 0
        elif pe >= 40 or pe < 0:
            score -= 10
        
        # PB评分 (低PB加分)
        if 0 < pb < 1.5:
            score += 15
        elif 1.5 <= pb < 3:
            score += 5
        elif pb >= 5:
            score -= 10
        
        # 市值评分 (中等市值加分)
        if 50 <= market_cap <= 500:
            score += 15
        elif 20 <= market_cap < 50 or 500 < market_cap <= 1000:
            score += 5
        
        return {
            'pe': pe,
            'pb': pb,
            'ps': row.get('市销率', 0) or 0,
            'market_cap': round(market_cap, 2),
            'score': min(max(score, 0), 100),  # 限制在0-100
        }
    except Exception as e:
        logger.debug(f"获取 {code} 估值数据失败: {e}")
        return {'pe': 0, 'pb': 0, 'ps': 0, 'market_cap': 0, 'score': 50}


# ============================================
# 5. 筹码因子 (v2.5.1 新增)
# ============================================

def get_shareholder_change_score(code: str) -> Dict:
    """
    计算股东人数变动评分 (筹码集中度辅助)
    
    逻辑：
    - 股东人数减少 -> 筹码集中 -> 加分
    - 股东人数增加 -> 筹码分散 -> 减分
    """
    try:
        # 这个接口获取股东人数历史变动
        df = ak.stock_zh_a_gdhs_detail_em(symbol=code)
        if df is None or len(df) < 2:
            return {'change_pct': 0, 'score': 50, 'label': '数据不足'}
            
        # 计算最新一期较上一期的变动幅度
        latest = df.iloc[0]['股东人数']
        prev = df.iloc[1]['股东人数']
        
        if prev > 0:
            change_pct = (latest - prev) / prev * 100
        else:
            change_pct = 0
            
        # 评分逻辑
        if change_pct < -5:
            score = 90
            label = f"✨筹码大幅集中({change_pct:.1f}%)"
        elif change_pct < -2:
            score = 75
            label = f"📈筹码趋向集中({change_pct:.1f}%)"
        elif change_pct > 5:
            score = 30
            label = f"⚠️筹码大幅分散({+change_pct:.1f}%)"
        else:
            score = 50
            label = "持平"
            
        return {
            'change_pct': round(change_pct, 2),
            'score': score,
            'label': label
        }
    except Exception as e:
        logger.debug(f"获取 {code} 股东人数失败: {e}")
        return {'change_pct': 0, 'score': 50, 'label': '查询失败'}


# ============================================
# 6. RPS 动量斜率因子 (v2.5.2 新增)
# ============================================

def calculate_rps_slope(rps_history: List[float], window: int = 5) -> Dict:
    """
    计算 RPS 动量斜率 (v2.5.2 策略师建议)
    
    逻辑：
    - 即便 RPS 为 90，如果斜率为负，说明动能正在衰减
    - 最优质的标的是 "RPS > 90 且斜率为正" 的股票，代表处于加速主升段
    
    Args:
        rps_history: 过去 N 天的 RPS 值列表 (最新的在最后)
        window: 计算斜率的窗口期 (默认 5 天)
    
    Returns:
        {
            'slope': float,           # 斜率值 (正=动能增强, 负=动能衰减)
            'is_accelerating': bool,  # 是否处于加速期
            'signal': str,            # 'ACCELERATE' (加速), 'DECELERATE' (减速), 'STABLE' (稳定)
            'score_adjustment': int,  # 评分调整值
            'label': str,             # 描述标签
        }
    """
    if not rps_history or len(rps_history) < 2:
        return {
            'slope': 0,
            'is_accelerating': False,
            'signal': 'UNKNOWN',
            'score_adjustment': 0,
            'label': '数据不足'
        }
    
    # 取最近 window 天的数据
    recent = rps_history[-window:] if len(rps_history) >= window else rps_history
    
    # 计算简单线性回归斜率
    # slope = (sum(xi * yi) - n * mean(x) * mean(y)) / (sum(xi^2) - n * mean(x)^2)
    n = len(recent)
    x = list(range(n))  # 0, 1, 2, ...
    y = recent
    
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
    
    if denominator == 0:
        slope = 0
    else:
        slope = numerator / denominator
    
    # 判断信号
    current_rps = recent[-1] if recent else 0
    
    if slope > 2:
        # 斜率显著为正：动能强劲增强
        signal = 'ACCELERATE'
        is_accelerating = True
        if current_rps >= 90:
            score_adjustment = 10  # RPS高+加速 = 核心标的
            label = f"🚀加速主升段(斜率+{slope:.1f})"
        elif current_rps >= 70:
            score_adjustment = 8
            label = f"📈动能增强(斜率+{slope:.1f})"
        else:
            score_adjustment = 5
            label = f"📈动能抬头(斜率+{slope:.1f})"
    elif slope > 0.5:
        # 斜率小幅为正：动能稳中向上
        signal = 'STABLE'
        is_accelerating = False
        score_adjustment = 3
        label = f"↗动能稳健(斜率+{slope:.1f})"
    elif slope < -2:
        # 斜率显著为负：动能快速衰减
        signal = 'DECELERATE'
        is_accelerating = False
        if current_rps >= 80:
            score_adjustment = -8  # 高RPS但衰减 = 警惕
            label = f"⚠️强势股退潮(斜率{slope:.1f})"
        else:
            score_adjustment = -5
            label = f"📉动能衰减(斜率{slope:.1f})"
    elif slope < -0.5:
        # 斜率小幅为负：动能趋弱
        signal = 'DECELERATE'
        is_accelerating = False
        score_adjustment = -3
        label = f"↘动能趋弱(斜率{slope:.1f})"
    else:
        # 斜率接近 0：动能持平
        signal = 'STABLE'
        is_accelerating = False
        score_adjustment = 0
        label = "→动能持平"
    
    return {
        'slope': round(slope, 2),
        'is_accelerating': is_accelerating,
        'signal': signal,
        'score_adjustment': score_adjustment,
        'label': label
    }


def get_rps_history_for_code(code: str, days: int = 5) -> List[float]:
    """
    获取指定股票过去 N 天的 RPS 历史值
    
    注意：这需要 RPS 历史数据。当前实现使用最新 RPS 文件，
    如需完整斜率计算，需要保存历史 RPS 数据。
    
    临时方案：使用 RPS 和 RPS 变动值估算
    """
    import glob
    from config.settings import RPS_DATA_DIR
    
    try:
        # 寻找最新的 RPS 文件
        list_of_files = sorted(glob.glob(os.path.join(RPS_DATA_DIR, 'rps_rank_*.csv')))
        if not list_of_files:
            return []
        
        # 尝试读取最近 N 天的文件
        rps_values = []
        for file in list_of_files[-days:]:
            try:
                df = pd.read_csv(file)
                # 兼容中英文列名
                code_col = 'code' if 'code' in df.columns else '代码'
                rps_col = 'rps' if 'rps' in df.columns else 'RPS'
                
                df[code_col] = df[code_col].astype(str).str.zfill(6)
                row = df[df[code_col] == str(code).zfill(6)]
                
                if not row.empty:
                    rps_val = row.iloc[0].get(rps_col, 0)
                    if pd.notna(rps_val):
                        rps_values.append(float(rps_val))
            except Exception:
                continue
        
        return rps_values
    except Exception as e:
        logger.debug(f"获取 {code} RPS 历史失败: {e}")
        return []



def calculate_multi_factor_score(
    code: str,
    name: str,
    rps: float,
    money_flow_score: float = None,
    sector_score: float = None,
    valuation_score: float = None,
    hot_sectors: List[Dict] = None,
) -> Dict:
    """
    计算多因子综合评分
    
    因子权重:
    - 动量因子(RPS): 30%
    - 资金流向: 25%
    - 板块热度: 20%
    - 估值因子: 15%
    - 技术因子: 10% (预留)
    
    Returns:
        {
            'total_score': float,      # 综合得分 (0-100)
            'rps_score': float,        # 动量得分
            'money_flow_score': float, # 资金得分
            'sector_score': float,     # 板块得分
            'valuation_score': float,  # 估值得分
            'grade': str,              # 评级 (A/B/C/D)
            'recommendation': str,     # 建议
        }
    """
    # 1. 动量因子 (RPS直接作为分数)
    rps_score = rps
    
    # 2. 资金流向因子
    if money_flow_score is None:
        mf = get_stock_money_flow(code)
        money_flow_score = mf['score']
    
    # 3. 板块热度因子
    if sector_score is None:
        if hot_sectors is None:
            hot_sectors = get_hot_sectors()
        sector_score = calculate_sector_score(code, hot_sectors)
    
    # 4. 估值因子
    if valuation_score is None:
        val = get_stock_valuation(code)
        valuation_score = val['score']
    
    # 计算加权总分
    total_score = (
        rps_score * 0.30 +
        money_flow_score * 0.25 +
        sector_score * 0.20 +
        valuation_score * 0.15 +
        50 * 0.10  # 技术因子暂用中性分
    )
    
    # 评级
    if total_score >= 80:
        grade = "A"
        recommendation = "强烈推荐，可重仓"
    elif total_score >= 70:
        grade = "B"
        recommendation = "推荐买入，可适量配置"
    elif total_score >= 60:
        grade = "C"
        recommendation = "中性，可少量参与"
    else:
        grade = "D"
        recommendation = "不推荐，建议观望"
    
    return {
        'code': code,
        'name': name,
        'total_score': round(total_score, 1),
        'rps_score': round(rps_score, 1),
        'money_flow_score': round(money_flow_score, 1),
        'sector_score': round(sector_score, 1),
        'valuation_score': round(valuation_score, 1),
        'grade': grade,
        'recommendation': recommendation,
    }


def batch_calculate_scores(stocks: List[Dict]) -> List[Dict]:
    """
    批量计算多因子评分 (v2.3 优化版)
    
    改进点：
    1. 大盘环境作为"折价因子"而非简单开关
    2. 检测"诱多信号"：RPS高但资金流出
    3. 板块共振加成更高
    
    Args:
        stocks: 股票列表，每个包含 代码, 名称, RPS
    
    Returns:
        带评分的股票列表
    """
    if not stocks:
        return []
    
    logger.info("📊 正在计算多因子评分 (v2.3 优化版)...")
    
    # =========================================
    # 1. 获取大盘环境折价系数
    # =========================================
    market_cond = get_market_condition()
    market_multiplier = 1.0  # 默认无折价
    
    if market_cond.get('safe', True):
        if market_cond.get('above_ma20') and market_cond.get('above_ma10'):
            market_multiplier = 1.0  # 上升趋势，正常
            logger.info("   📈 大盘环境: 上升趋势 → 评分系数 ×1.0")
        else:
            market_multiplier = 0.9  # 震荡，轻微折价
            logger.info("   📊 大盘环境: 震荡市 → 评分系数 ×0.9")
    else:
        if market_cond.get('index_change', 0) < -2:
            market_multiplier = 0.5  # 大盘暴跌，严重折价
            logger.info("   ⚠️ 大盘环境: 急跌 → 评分系数 ×0.5")
        else:
            market_multiplier = 0.7  # 下降趋势，折价
            logger.info("   ⚠️ 大盘环境: 下降趋势 → 评分系数 ×0.7")
    
    # =========================================
    # 2. 预先获取热门板块
    # =========================================
    hot_sectors = get_hot_sectors(10)
    hot_sector_names = [s['name'] for s in hot_sectors[:5]]
    logger.info(f"   🔥 热门板块TOP5: {', '.join(hot_sector_names)}")
    
    # 创建板块名称到排名的映射
    sector_rank_map = {s['name']: s['rank'] for s in hot_sectors}
    
    # =========================================
    # 3. 预先获取资金流入排行和流出排行
    # =========================================
    money_flow_df = get_money_flow_rank(300)  # 获取更多数据
    money_inflow_set = set()  # 资金流入的股票
    if not money_flow_df.empty:
        money_inflow_set = set(money_flow_df['code'].tolist())
    
    # 获取资金流出的股票（用于诱多检测）
    money_outflow_set = set()
    try:
        outflow_df = ak.stock_individual_fund_flow_rank(indicator="今日")
        if outflow_df is not None and not outflow_df.empty:
            # 确保数值类型
            outflow_df['今日主力净流入-净额'] = pd.to_numeric(outflow_df['今日主力净流入-净额'], errors='coerce').fillna(0)
            # 主力净流出超过1000万的
            outflow_df = outflow_df[outflow_df['今日主力净流入-净额'] < -1000]
            money_outflow_set = set(outflow_df['代码'].astype(str).str.zfill(6).tolist())
    except Exception as e:
        logger.debug(f"获取资金流出数据失败: {e}")
    
    logger.info(f"   💰 资金流入股票: {len(money_inflow_set)} 只 | 资金流出: {len(money_outflow_set)} 只")
    
    # =========================================
    # 4. 预先获取全市场估值数据 (v2.4.2 性能优化)
    # =========================================
    logger.info("   📊 正在批量获取全市场估值数据...")
    valuation_map = {}
    try:
        # 一次性拉取全市场实时数据，包含PE/PB/市值等
        # 使用 stock_zh_a_spot_em 接口获取实时行情，其中包含动态市盈率、市净率、总市值
        spot_df = ak.stock_zh_a_spot_em()
        
        if spot_df is not None and not spot_df.empty:
            # 建立映射: code -> row data
            # 代码需要标准化为6位字符串
            spot_df['代码'] = spot_df['代码'].astype(str).str.zfill(6)
            
            # 为了加速，我们可以只保留我们关心的列，并转换为字典
            # 注意: 不同版本的 akshare 返回列名可能略有差异，这里做防御性处理
            needed_cols = ['代码', '市盈率-动态', '市净率', '市销率', '总市值']
            available_cols = [c for c in needed_cols if c in spot_df.columns]
            
            if len(available_cols) > 1:
                # 转换为字典: { '000001': {'市盈率-动态': 10.5, ...}, ... }
                # orient='index' 会以索引为key，所以先设代码为索引
                valuation_map = spot_df.set_index('代码')[available_cols[1:]].to_dict('index')
                logger.info(f"   ✅ 已缓存 {len(valuation_map)} 只股票的估值数据")
            else:
                logger.warning("   ⚠️ 获取全市场估值数据失败: 缺少必要字段")
    except Exception as e:
        logger.warning(f"   ⚠️ 批量获取估值数据失败 (将回退到逐个获取): {e}")

    # =========================================
    # 5. 批量计算评分
    # =========================================
    results = []
    trap_count = 0  # 诱多信号计数
    
    for s in stocks:
        code = s.get('code', '')
        name = s.get('name', '')
        rps = s.get('rps', 50)
        
        # --- 基础分计算 ---
        base_score = rps  # RPS作为基础分 (30%)
        
        # --- 资金流向评分 ---
        if code in money_inflow_set:
            money_flow_score = 90  # 资金流入，高分
        elif code in money_outflow_set:
            money_flow_score = 20  # 资金流出，低分
        else:
            money_flow_score = 50  # 中性
        
        # --- ⚠️ 诱多信号检测 ---
        is_trap = False
        if rps >= 80 and code in money_outflow_set:
            # RPS很高但主力在出货 = 诱多！
            is_trap = True
            trap_count += 1
            money_flow_score = 10  # 严厉惩罚
        
        # --- 板块共振评分 (使用RPS数据中的板块信息，避免API调用) ---
        sector_score = 50  # 默认
        try:
            # 优先使用传入数据中的板块信息
            sector = s.get('sector', '')
            if sector:
                for hot in hot_sectors:
                    if hot['name'] in sector or sector in hot['name']:
                        rank = hot['rank']
                        if rank <= 3:
                            sector_score = 100  # TOP3板块，满分
                        elif rank <= 5:
                            sector_score = 90   # TOP5板块
                        elif rank <= 10:
                            sector_score = 75   # TOP10板块
                        break
        except Exception as e:
            logger.debug(f"计算 {code} 板块共振评分失败: {e}")
        
        # --- 估值评分 (v2.4.2: 使用预加载数据极速计算) ---
        valuation_score = 50  # 默认中性分
        try:
            val_data = valuation_map.get(code)
            if val_data:
                # 提取数据 (v2.5.1: 采用标准化英文键)
                pe = val_data.get('pe', 0) or 0
                pb = val_data.get('pb', 0) or 0
                market_cap = (val_data.get('market_cap', 0) or 0) / 100000000  # 转为亿
                
                # PE评分 (低PE加分)
                if 0 < pe < 15: valuation_score += 20
                elif 15 <= pe < 25: valuation_score += 10
                elif 25 <= pe < 40: valuation_score += 0
                elif pe >= 40 or pe < 0: valuation_score -= 10
                
                # PB评分 (低PB加分)
                if 0 < pb < 1.5: valuation_score += 15
                elif 1.5 <= pb < 3: valuation_score += 5
                elif pb >= 5: valuation_score -= 10
                
                # 市值评分 (50-500亿中盘股加分)
                if 50 <= market_cap <= 500: valuation_score += 15
                elif 20 <= market_cap < 50 or 500 < market_cap <= 1000: valuation_score += 5
                
                # 限制范围
                valuation_score = min(max(valuation_score, 0), 100)
        except Exception:
            pass  # 计算失败保持默认 50 分
        
        # --- 量能因子评分 (v2.4 新增) ---
        volume_energy_score = 50  # 默认中性分
        volume_features = []
        try:
            # 从传入的数据中获取量比
            volume_ratio = s.get('volume_ratio', 1.0)
            
            # 简化版量能评分：基于量比
            if volume_ratio >= 2.0:
                volume_energy_score = 75
                volume_features.append("放量")
            elif volume_ratio >= 1.2:
                volume_energy_score = 60
                volume_features.append("温和放量")
            elif volume_ratio <= 0.5:
                volume_energy_score = 30
                volume_features.append("缩量")
        except Exception as e:
            logger.debug(f"计算 {code} 量能评分失败: {e}")
        
        # --- 加权计算总分 (v2.4 调整权重) ---
        raw_score = (
            base_score * 0.25 +          # 动量 25% (从30%降低)
            money_flow_score * 0.25 +    # 资金 25%
            sector_score * 0.20 +        # 板块 20% (从25%降低)
            valuation_score * 0.10 +     # 估值 10%
            volume_energy_score * 0.10 + # 量能 10% (替代预留的技术因子)
            50 * 0.10                    # 技术形态 10% (预留)
        )
        
        # --- 应用大盘折价系数 ---
        total_score = raw_score * market_multiplier
        
        # --- 评级 ---
        if is_trap:
            grade = "⚠️"
            recommendation = "警告：疑似诱多，主力资金正在出货！"
        elif total_score >= 80:
            grade = "A"
            recommendation = "强烈推荐，可重仓"
        elif total_score >= 70:
            grade = "B"
            recommendation = "推荐买入，可适量配置"
        elif total_score >= 60:
            grade = "C"
            recommendation = "中性，可少量参与"
        else:
            grade = "D"
            recommendation = "不推荐，建议观望"
        
        # 合并结果
        result = {
            **s,
            'code': code,
            'name': name,
            'total_score': round(total_score, 1),
            'raw_score': round(raw_score, 1),  # 折价前分数
            'rps_score': round(rps, 1),
            'money_flow_score': round(money_flow_score, 1),
            'sector_score': round(sector_score, 1),
            'valuation_score': round(valuation_score, 1),
            'volume_energy_score': round(volume_energy_score, 1),
            'volume_features': volume_features,
            'market_multiplier': market_multiplier,
            'is_trap': is_trap,
            'grade': grade,
            'recommendation': recommendation,
        }
        results.append(result)
    
    # 过滤诱多信号 (可选：直接排除)
    if trap_count > 0:
        logger.warning(f"   ⚠️ 检测到 {trap_count} 只疑似诱多股票！")
    
    # 按综合得分排序
    results.sort(key=lambda x: (not x['is_trap'], x['total_score']), reverse=True)
    
    logger.info(f"   ✅ 评分完成: {len(results)} 只股票")
    
    return results


if __name__ == "__main__":
    # 测试
    print_market_condition()
    
    print("\n热门板块:")
    for s in get_hot_sectors(5):
        print(f"  {s['rank']}. {s['name']} {s['change']:+.2f}%")


# ============================================
# 6. 板块效应统计 (v2.4 新增)
# ============================================

def analyze_sector_cluster(stocks: List[Dict]) -> Dict:
    """
    分析选股结果中的板块聚类效应 (v2.4 新增)
    
    策略报告建议:
    如果选出的股票中有多只属于同一板块，说明该板块具备共识，
    这些票的胜率会远高于其他杂毛股票。
    
    Args:
        stocks: 选股结果列表，每个包含 '代码', '名称', '板块' 等字段
    
    Returns:
        {
            'cluster_found': bool,       # 是否发现板块聚类
            'dominant_sector': str,      # 主导板块名称
            'dominant_count': int,       # 主导板块股票数量
            'sector_distribution': dict, # 各板块分布 {板块名: [股票列表]}
            'recommendation': str,       # 操作建议
        }
    """
    if not stocks:
        return {'cluster_found': False, 'recommendation': '无数据'}
    
    # 统计各板块的股票
    sector_map: Dict[str, List[Dict]] = {}
    
    for s in stocks:
        sector = s.get('板块', '') or s.get('sector', '')
        if not sector:
            sector = '未知板块'
        
        if sector not in sector_map:
            sector_map[sector] = []
        sector_map[sector].append({
            'code': s.get('代码', ''),
            'name': s.get('名称', ''),
            'rps': s.get('RPS', 0),
            'score': s.get('total_score', 0),
        })
    
    # 按股票数量排序
    sorted_sectors = sorted(sector_map.items(), key=lambda x: len(x[1]), reverse=True)
    
    # 判断是否存在板块聚类
    total_stocks = len(stocks)
    dominant_sector, dominant_stocks = sorted_sectors[0] if sorted_sectors else ('', [])
    dominant_count = len(dominant_stocks)
    
    # 聚类判定：某板块占比超过30%或数量>=3
    cluster_found = dominant_count >= 3 or (dominant_count >= 2 and dominant_count / total_stocks >= 0.3)
    
    # 生成建议
    if cluster_found:
        recommendation = f"🎯 板块共振！{dominant_sector} 板块有 {dominant_count} 只股票入选，这些票的胜率更高，可重点关注"
    else:
        recommendation = "📊 个股分散，无明显板块聚类"
    
    return {
        'cluster_found': cluster_found,
        'dominant_sector': dominant_sector,
        'dominant_count': dominant_count,
        'sector_distribution': dict(sorted_sectors),
        'recommendation': recommendation,
    }


def print_sector_cluster_report(stocks: List[Dict]):
    """打印板块聚类分析报告"""
    result = analyze_sector_cluster(stocks)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 板块效应分析 (v2.4)")
    logger.info("=" * 60)
    
    if result['cluster_found']:
        logger.info(f"   🎯 发现板块共振！")
        logger.info(f"   主导板块: {result['dominant_sector']} ({result['dominant_count']} 只)")
        
        # 展示主导板块中的股票
        dominant_stocks = result['sector_distribution'].get(result['dominant_sector'], [])
        for s in dominant_stocks:
            logger.info(f"      - {s['code']} {s['name']} | RPS={s['rps']:.1f}")
    else:
        logger.info(f"   📊 无明显板块聚类")
    
    # 展示板块分布
    logger.info(f"\n   板块分布:")
    for sector, stocks_in_sector in result['sector_distribution'].items():
        if sector != '未知板块':
            logger.info(f"      {sector}: {len(stocks_in_sector)} 只")
    
    logger.info(f"\n   💡 {result['recommendation']}")
    logger.info("=" * 60)
    
    return result


# ============================================
# 7. 大盘总开关 (v2.4 增强)
# ============================================

def should_stop_trading() -> Tuple[bool, str]:
    """
    大盘总开关：检查是否应该停止交易 (v2.4)
    
    策略报告建议:
    在熊市里，最好的操作是空仓。系统需要一个"总开关"来抑制
    在系统性风险下的开仓冲动。
    
    Returns:
        (should_stop: bool, reason: str)
    """
    try:
        from config import MARKET_RISK_CONTROL
        
        # 获取大盘状态
        market_cond = get_market_condition()
        
        # 检查总开关是否启用
        if not MARKET_RISK_CONTROL.get('enabled', True):
            return False, "大盘风控已禁用"
        
        # 1. 检查大盘是否在20日均线之下
        if not market_cond.get('above_ma20', True):
            action = MARKET_RISK_CONTROL.get('below_ma20_action', 'warn')
            if action == 'stop':
                return True, f"大盘跌破20日均线（空头趋势），建议停止交易"
        
        # 2. 检查大盘是否急跌
        drop_threshold = MARKET_RISK_CONTROL.get('index_drop_threshold', -2.0)
        if market_cond.get('index_change', 0) < drop_threshold:
            return True, f"大盘急跌 {market_cond.get('index_change'):.2f}%，建议停止交易"
        
        # 3. 检查休眠模式
        sleep_mode = MARKET_RISK_CONTROL.get('sleep_mode', {})
        if sleep_mode.get('enabled', False):
            trigger = sleep_mode.get('trigger', 'below_ma20')
            if trigger == 'below_ma20' and not market_cond.get('above_ma20', True):
                return True, "触发休眠模式：大盘在20日均线之下"
        
        # 4. 综合检查
        if not market_cond.get('safe', True):
            return True, market_cond.get('suggestion', '市场风险较高')
        
        return False, "大盘状态正常，可以交易"
        
    except Exception as e:
        logger.error(f"大盘总开关检查失败: {e}")
        # 出错时保守处理，返回停止交易
        return True, f"大盘检查异常: {e}"


def check_market_and_decide() -> Dict:
    """
    综合检查大盘状态并给出交易决策 (v2.4)
    
    Returns:
        {
            'can_trade': bool,       # 是否可以交易
            'risk_level': str,       # 风险等级 (low/medium/high/extreme)
            'position_ratio': float, # 建议仓位比例 (0-1)
            'reason': str,           # 原因说明
        }
    """
    try:
        market_cond = get_market_condition()
        
        should_stop, reason = should_stop_trading()
        
        if should_stop:
            return {
                'can_trade': False,
                'risk_level': 'extreme',
                'position_ratio': 0,
                'reason': reason,
            }
        
        # 根据大盘状态调整仓位比例
        if market_cond.get('above_ma20') and market_cond.get('above_ma10'):
            # 上升趋势
            return {
                'can_trade': True,
                'risk_level': 'low',
                'position_ratio': 1.0,
                'reason': '大盘上升趋势，可正常交易',
            }
        elif market_cond.get('above_ma20'):
            # 震荡偏强
            return {
                'can_trade': True,
                'risk_level': 'medium',
                'position_ratio': 0.7,
                'reason': '大盘震荡，建议减少仓位30%',
            }
        else:
            # 下降趋势但未触发停止
            return {
                'can_trade': True,
                'risk_level': 'high',
                'position_ratio': 0.5,
                'reason': '大盘偏弱，建议轻仓操作',
            }
            
    except Exception as e:
        logger.error(f"交易决策检查失败: {e}")
        return {
            'can_trade': False,
            'risk_level': 'extreme',
            'position_ratio': 0,
            'reason': f'检查异常: {e}',
        }

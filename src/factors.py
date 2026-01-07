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
        }
    except Exception as e:
        logger.error(f"获取大盘状态失败: {e}")
        return {'safe': False, 'trend': f'错误: {e}', 'suggestion': '暂停交易'}


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
    
    logger.info("=" * 60)
    return cond


# ============================================
# 2. 资金流向因子
# ============================================

def get_money_flow_rank(top_n: int = 100) -> pd.DataFrame:
    """
    获取主力资金流入排行
    
    Returns:
        DataFrame with columns: 代码, 名称, 主力净流入, 主力净流入占比
    """
    try:
        # 获取个股资金流排名
        df = ak.stock_individual_fund_flow_rank(indicator="今日")
        
        if df is None or df.empty:
            logger.warning("资金流向数据获取失败")
            return pd.DataFrame()
        
        # 筛选主力净流入为正的股票
        df = df[df['主力净流入-净额'] > 0].head(top_n)
        
        # 标准化列名
        result = pd.DataFrame({
            '代码': df['代码'].astype(str).str.zfill(6),
            '名称': df['名称'],
            '主力净流入': df['主力净流入-净额'],
            '主力净流入占比': df['主力净流入-净占比'],
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
    except:
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


def get_stock_sector(code: str) -> Optional[str]:
    """获取股票所属行业板块"""
    try:
        df = ak.stock_individual_info_em(symbol=code)
        if df is not None and '所属行业' in df['item'].values:
            return df[df['item'] == '所属行业']['value'].iloc[0]
    except:
        pass
    return None


def get_sector_stocks(sector_name: str) -> List[str]:
    """获取板块内的股票代码列表"""
    try:
        df = ak.stock_board_industry_cons_em(symbol=sector_name)
        if df is not None and not df.empty:
            return df['代码'].tolist()
    except:
        pass
    return []


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
    except:
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
    except:
        return {'pe': 0, 'pb': 0, 'ps': 0, 'market_cap': 0, 'score': 50}


# ============================================
# 5. 多因子综合评分
# ============================================

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
        money_inflow_set = set(money_flow_df['代码'].tolist())
    
    # 获取资金流出的股票（用于诱多检测）
    money_outflow_set = set()
    try:
        outflow_df = ak.stock_individual_fund_flow_rank(indicator="今日")
        if outflow_df is not None and not outflow_df.empty:
            # 主力净流出超过1000万的
            outflow_df = outflow_df[outflow_df['主力净流入-净额'] < -1000]
            money_outflow_set = set(outflow_df['代码'].astype(str).str.zfill(6).tolist())
    except:
        pass
    
    logger.info(f"   💰 资金流入股票: {len(money_inflow_set)} 只 | 资金流出: {len(money_outflow_set)} 只")
    
    # =========================================
    # 4. 批量计算评分
    # =========================================
    results = []
    trap_count = 0  # 诱多信号计数
    
    for s in stocks:
        code = s.get('代码', '')
        name = s.get('名称', '')
        rps = s.get('RPS', 50)
        
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
        
        # --- 板块共振评分 (加大权重) ---
        sector_score = 50  # 默认
        try:
            sector = get_stock_sector(code)
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
        except:
            pass
        
        # --- 估值评分 ---
        valuation_score = 50
        try:
            val = get_stock_valuation(code)
            valuation_score = val['score']
        except:
            pass
        
        # --- 加权计算总分 ---
        raw_score = (
            base_score * 0.30 +          # 动量 30%
            money_flow_score * 0.25 +    # 资金 25%
            sector_score * 0.25 +        # 板块 25% (从20%提高)
            valuation_score * 0.10 +     # 估值 10% (从15%降低)
            50 * 0.10                    # 技术 10% (预留)
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

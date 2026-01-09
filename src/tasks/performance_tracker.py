#!/usr/bin/env python
"""
推荐效果追踪模块 (Performance Tracker)
功能：
1. 自动记录每日推荐的股票
2. 追踪推荐后1日、3日、5日的涨跌幅
3. 统计胜率、平均收益率
4. 生成周报/月报
"""
import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config import PERFORMANCE_TRACKING, RESULTS_DIR
from config import PERFORMANCE_TRACKING, RESULTS_DIR
from src.utils import logger
from src.database import db
from src.data_loader import get_realtime_quotes


def load_recommendations_v2() -> List[Dict]:
    """获取所有原始推荐记录 (数据库格式)"""
    return db.get_recommendations()


def load_recommendations() -> Dict:
    """
    加载推荐记录并转换为旧的 Dict 结构以保持逻辑兼容
    Struct: { '2026-01-08': {'stocks': [...]} }
    """
    recs = db.get_recommendations()
    legacy_format = {}
    for r in recs:
        date = r['date']
        if date not in legacy_format:
            legacy_format[date] = {'stocks': []}
        
        legacy_format[date]['stocks'].append({
            'code': r['code'],
            'name': r['name'],
            'price': r['buy_price'],
            'rps': r['rps'],
            'category': r['category'],
            'suggestion': r['suggestion'],
            'day1_pnl': r.get('day1_pnl'),
            'day3_pnl': r.get('day3_pnl'),
            'day5_pnl': r.get('day5_pnl'),
        })
    return legacy_format


def save_recommendations(data: Dict):
    """保存推荐记录 (v2.5.1: 写入数据库)"""
    for date, content in data.items():
        for s in content['stocks']:
            db.save_recommendation({
                'date': date,
                'code': s['code'],
                'name': s['name'],
                'buy_price': s.get('price', 0),
                'rps': s.get('rps', 0),
                'category': s.get('category', ''),
                'suggestion': s.get('suggestion', ''),
                'day1_pnl': s.get('day1_pnl'),
                'day3_pnl': s.get('day3_pnl'),
                'day5_pnl': s.get('day5_pnl'),
            })


def record_daily_recommendations(stocks: List[Dict]):
    """
    记录当日推荐的股票
    """
    if not stocks:
        return
    
    today = datetime.now().strftime('%Y-%m-%d')
    added = 0
    for s in stocks:
        db.save_recommendation({
            'date': today,
            'code': s.get('代码', ''),
            'name': s.get('名称', ''),
            'buy_price': s.get('现价', 0),
            'rps': s.get('RPS', 0),
            'category': s.get('分类', ''),
            'suggestion': s.get('建议', ''),
        })
        added += 1
    
    logger.info(f"📝 已在数据库中记录 {added} 只推荐股票 ({today})")


def get_stock_price(code: str) -> Optional[float]:
    """获取股票当前价格 (v2.5.1)"""
    try:
        df = get_realtime_quotes()
        stock = df[df['code'] == code]
        if not stock.empty:
            return stock.iloc[0]['close']
    except Exception:
        pass
    return None


def update_performance_tracking():
    """
    更新推荐效果追踪
    检查过去的推荐，更新1日、3日、5日的表现
    """
    recommendations = load_recommendations()
    
    if not recommendations:
        logger.info("📭 暂无推荐记录")
        return
    
    today = datetime.now().date()
    updated = False
    
    for date_str, data in recommendations.items():
        try:
            rec_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            continue
        
        days_passed = (today - rec_date).days
        
        # 跳过太旧的记录 (超过10天不再更新)
        if days_passed > 10:
            continue
        
        for stock in data['stocks']:
            code = stock['code']
            buy_price = stock['price']
            
            if buy_price <= 0:
                continue
            
            current_price = get_stock_price(code)
            if current_price is None:
                continue
            
            # 根据天数更新相应字段
            if days_passed >= 1 and stock.get('day1_price') is None:
                stock['day1_price'] = current_price
                stock['day1_pnl'] = round((current_price - buy_price) / buy_price * 100, 2)
                updated = True
                logger.info(f"  📊 {code} {stock['name']} 1日: {stock['day1_pnl']:+.2f}%")
            
            if days_passed >= 3 and stock.get('day3_price') is None:
                stock['day3_price'] = current_price
                stock['day3_pnl'] = round((current_price - buy_price) / buy_price * 100, 2)
                updated = True
                logger.info(f"  📊 {code} {stock['name']} 3日: {stock['day3_pnl']:+.2f}%")
            
            if days_passed >= 5 and stock.get('day5_price') is None:
                stock['day5_price'] = current_price
                stock['day5_pnl'] = round((current_price - buy_price) / buy_price * 100, 2)
                updated = True
                logger.info(f"  📊 {code} {stock['name']} 5日: {stock['day5_pnl']:+.2f}%")
    
    if updated:
        save_recommendations(recommendations)
        logger.info("✅ 效果追踪已更新")
    else:
        logger.info("ℹ️ 暂无需要更新的记录")


def calculate_statistics() -> Dict:
    """
    计算推荐效果统计
    
    Returns:
        统计数据字典
    """
    recommendations = load_recommendations()
    
    if not recommendations:
        return {}
    
    # 收集所有有效数据
    day1_data = []
    day3_data = []
    day5_data = []
    
    # 按类别统计
    category_stats = {}
    
    for date_str, data in recommendations.items():
        for stock in data['stocks']:
            category = stock.get('category', '未知')
            
            if category not in category_stats:
                category_stats[category] = {
                    'count': 0,
                    'day1_pnls': [],
                    'day3_pnls': [],
                    'day5_pnls': []
                }
            
            category_stats[category]['count'] += 1
            
            if stock.get('day1_pnl') is not None:
                day1_data.append(stock['day1_pnl'])
                category_stats[category]['day1_pnls'].append(stock['day1_pnl'])
            
            if stock.get('day3_pnl') is not None:
                day3_data.append(stock['day3_pnl'])
                category_stats[category]['day3_pnls'].append(stock['day3_pnl'])
            
            if stock.get('day5_pnl') is not None:
                day5_data.append(stock['day5_pnl'])
                category_stats[category]['day5_pnls'].append(stock['day5_pnl'])
    
    def calc_stats(pnl_list):
        if not pnl_list:
            return None
        return {
            'count': len(pnl_list),
            'win_rate': round(sum(1 for p in pnl_list if p > 0) / len(pnl_list) * 100, 1),
            'avg_pnl': round(sum(pnl_list) / len(pnl_list), 2),
            'max_profit': round(max(pnl_list), 2),
            'max_loss': round(min(pnl_list), 2),
        }
    
    stats = {
        'updated_at': datetime.now().isoformat(),
        'total_recommendations': sum(len(d['stocks']) for d in recommendations.values()),
        'total_days': len(recommendations),
        'overall': {
            'day1': calc_stats(day1_data),
            'day3': calc_stats(day3_data),
            'day5': calc_stats(day5_data),
        },
        'by_category': {}
    }
    
    for category, data in category_stats.items():
        stats['by_category'][category] = {
            'count': data['count'],
            'day1': calc_stats(data['day1_pnls']),
            'day3': calc_stats(data['day3_pnls']),
            'day5': calc_stats(data['day5_pnls']),
        }
    
    # 返回统计结果
    return stats


def print_performance_report():
    """打印效果报告"""
    stats = calculate_statistics()
    
    if not stats:
        logger.info("📭 暂无统计数据")
        return
    
    logger.info("=" * 70)
    logger.info("📊 推荐效果统计报告")
    logger.info(f"📅 更新时间: {stats['updated_at'][:19]}")
    logger.info("=" * 70)
    
    logger.info(f"\n📈 总览:")
    logger.info(f"   推荐总数: {stats['total_recommendations']} 只")
    logger.info(f"   统计天数: {stats['total_days']} 天")
    
    # 整体表现
    logger.info(f"\n📊 整体表现:")
    for period, label in [('day1', '次日'), ('day3', '3日'), ('day5', '5日')]:
        data = stats['overall'].get(period)
        if data:
            emoji = "🟢" if data['avg_pnl'] > 0 else "🔴"
            logger.info(f"   {label}: {emoji} 胜率 {data['win_rate']}% | 平均收益 {data['avg_pnl']:+.2f}% | 最高 {data['max_profit']:+.2f}% | 最低 {data['max_loss']:+.2f}%")
        else:
            logger.info(f"   {label}: 数据不足")
    
    # 按类别表现
    logger.info(f"\n📋 分类表现:")
    for category, data in stats['by_category'].items():
        logger.info(f"\n   {category} ({data['count']}只):")
        for period, label in [('day1', '次日'), ('day3', '3日'), ('day5', '5日')]:
            pdata = data.get(period)
            if pdata:
                emoji = "🟢" if pdata['avg_pnl'] > 0 else "🔴"
                logger.info(f"      {label}: {emoji} 胜率 {pdata['win_rate']}% | 平均 {pdata['avg_pnl']:+.2f}%")
    
    logger.info("\n" + "=" * 70)


def format_performance_message(stats: Dict) -> str:
    """格式化效果统计消息 (用于推送)"""
    if not stats:
        return "暂无统计数据"
    
    lines = [
        f"📅 更新时间: {stats['updated_at'][:10]}\n",
        f"📈 **推荐总览**",
        f"- 推荐总数: {stats['total_recommendations']} 只",
        f"- 统计天数: {stats['total_days']} 天\n",
        "### 📊 整体表现\n"
    ]
    
    for period, label in [('day1', '次日'), ('day3', '3日'), ('day5', '5日')]:
        data = stats['overall'].get(period)
        if data:
            emoji = "🟢" if data['avg_pnl'] > 0 else "🔴"
            lines.append(f"**{label}**: {emoji} 胜率 {data['win_rate']}% | 平均 {data['avg_pnl']:+.2f}%")
    
    lines.append("\n### 📋 分类表现\n")
    
    for category, data in stats['by_category'].items():
        day1 = data.get('day1')
        if day1:
            emoji = "🟢" if day1['avg_pnl'] > 0 else "🔴"
            lines.append(f"**{category}**: {emoji} 次日胜率 {day1['win_rate']}% | 平均 {day1['avg_pnl']:+.2f}%")
    
    return "\n".join(lines)


def run_performance_tracker(push: bool = False):
    """
    运行效果追踪
    
    Args:
        push: 是否推送报告
    """
    logger.info("=" * 60)
    logger.info("📊 推荐效果追踪")
    logger.info(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 1. 更新追踪数据
    logger.info("\n[1/2] 📈 更新效果追踪...")
    update_performance_tracking()
    
    # 2. 生成统计报告
    logger.info("\n[2/2] 📊 生成统计报告...")
    stats = calculate_statistics()
    print_performance_report()
    
    # 3. 推送报告
    if push and stats:
        try:
            from src.notifier import notify_all
            message = format_performance_message(stats)
            notify_all("📊 推荐效果周报", message)
            logger.info("\n📱 报告已推送")
        except Exception as e:
            logger.error(f"推送失败: {e}")


def cleanup_old_recommendations(days: int = 30):
    """清理超过指定天数的旧推荐记录"""
    recommendations = load_recommendations()
    
    if not recommendations:
        return
    
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    old_count = len(recommendations)
    new_recommendations = {
        k: v for k, v in recommendations.items()
        if k >= cutoff
    }
    
    removed = old_count - len(new_recommendations)
    if removed > 0:
        save_recommendations(new_recommendations)
        logger.info(f"🧹 已清理 {removed} 条过期推荐记录")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='推荐效果追踪')
    parser.add_argument('--update', action='store_true', help='更新追踪数据')
    parser.add_argument('--report', action='store_true', help='生成报告')
    parser.add_argument('--push', action='store_true', help='推送报告')
    parser.add_argument('--cleanup', type=int, help='清理超过N天的记录')
    
    args = parser.parse_args()
    
    if args.cleanup:
        cleanup_old_recommendations(args.cleanup)
    elif args.update:
        update_performance_tracking()
    elif args.report:
        print_performance_report()
    else:
        run_performance_tracker(push=args.push)

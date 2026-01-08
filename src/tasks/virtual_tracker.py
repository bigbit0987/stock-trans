#!/usr/bin/env python
"""
虚拟持仓追踪模块 (Virtual Position Tracker)
功能：
1. 自动将推荐股票加入"虚拟持仓"进行追踪
2. 结合技术指标判断卖点
3. 自动记录涨跌结果
4. 用于验证策略效果，无需真正买入
"""
import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config import REALTIME_MONITOR
from src.utils import logger


# 虚拟持仓文件
VIRTUAL_POSITIONS_FILE = os.path.join(PROJECT_ROOT, "data", "virtual_positions.json")
# 虚拟交易记录
VIRTUAL_TRADES_FILE = os.path.join(PROJECT_ROOT, "data", "virtual_trades.json")


def load_virtual_positions() -> Dict:
    """加载虚拟持仓"""
    if os.path.exists(VIRTUAL_POSITIONS_FILE):
        try:
            with open(VIRTUAL_POSITIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_virtual_positions(positions: Dict):
    """保存虚拟持仓"""
    os.makedirs(os.path.dirname(VIRTUAL_POSITIONS_FILE), exist_ok=True)
    with open(VIRTUAL_POSITIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)


def load_virtual_trades() -> List[Dict]:
    """加载虚拟交易记录"""
    if os.path.exists(VIRTUAL_TRADES_FILE):
        try:
            with open(VIRTUAL_TRADES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_virtual_trades(trades: List[Dict]):
    """保存虚拟交易记录"""
    os.makedirs(os.path.dirname(VIRTUAL_TRADES_FILE), exist_ok=True)
    with open(VIRTUAL_TRADES_FILE, 'w', encoding='utf-8') as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)


def add_recommendations_to_virtual(stocks: List[Dict]):
    """
    将当日推荐股票自动加入虚拟持仓
    
    Args:
        stocks: 选股结果列表
    """
    if not stocks:
        return
    
    positions = load_virtual_positions()
    today = datetime.now().strftime('%Y-%m-%d')
    added_count = 0
    
    for s in stocks:
        code = s.get('代码', '')
        if not code:
            continue
        
        # 如果已存在且未平仓，跳过
        if code in positions and not positions[code].get('closed', False):
            continue
        
        positions[code] = {
            'name': s.get('名称', ''),
            'buy_price': s.get('现价', 0),
            'buy_date': today,
            'rps': s.get('RPS', 0),
            'category': s.get('分类', ''),
            'suggestion': s.get('建议', ''),
            'highest_price': s.get('现价', 0),
            'lowest_price': s.get('现价', 0),
            'closed': False,
            'close_date': None,
            'close_price': None,
            'close_reason': None,
            'pnl_pct': None,
        }
        added_count += 1
    
    save_virtual_positions(positions)
    logger.info(f"📥 已将 {added_count} 只推荐股票加入虚拟持仓追踪")


def get_stock_technical_data(code: str) -> Optional[Dict]:
    """
    获取股票技术指标数据 (v2.3.1 增强版)
    
    Returns:
        包含MA5, MA10, MA20, ATR, 当前价等技术数据
    """
    try:
        # 获取实时价格
        df = ak.stock_zh_a_spot_em()
        stock = df[df['代码'] == code]
        if stock.empty:
            return None
        
        current_price = stock.iloc[0]['最新价']
        pct_change = stock.iloc[0]['涨跌幅']
        
        # 获取历史数据计算均线和ATR
        hist = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if hist is None or len(hist) < 20:
            return None
        
        # 排除今天的数据避免重复
        today_str = datetime.now().strftime('%Y-%m-%d')
        hist['日期_str'] = pd.to_datetime(hist['日期']).dt.strftime('%Y-%m-%d')
        if not hist.empty and hist.iloc[-1]['日期_str'] == today_str:
            hist = hist.iloc[:-1]
        
        if len(hist) < 20:
            return None
        
        closes = hist['收盘'].tolist()
        highs = hist['最高'].tolist()
        lows = hist['最低'].tolist()
        
        # 计算实时均线 (加入当前价)
        ma5 = (sum(closes[-4:]) + current_price) / 5
        ma10 = (sum(closes[-9:]) + current_price) / 10
        ma20 = (sum(closes[-19:]) + current_price) / 20
        
        # 计算ATR (v2.3.1 新增)
        from src.indicators import calculate_atr
        atr = calculate_atr(highs, lows, closes, period=14)
        atr_pct = (atr / current_price * 100) if current_price > 0 else 0
        
        # 计算K线形态
        prev_close = closes[-1]
        prev_open = hist.iloc[-1]['开盘']
        is_prev_red = prev_close > prev_open  # 昨日阳线
        
        # 计算成交量趋势
        volumes = hist['成交量'].tail(5).tolist()
        avg_volume = sum(volumes) / len(volumes)
        
        return {
            'current_price': current_price,
            'pct_change': pct_change,
            'ma5': ma5,
            'ma10': ma10,
            'ma20': ma20,
            'atr': atr,                    # v2.3.1 新增
            'atr_pct': round(atr_pct, 2),  # v2.3.1 新增
            'prev_close': prev_close,
            'is_above_ma5': current_price > ma5,
            'is_above_ma10': current_price > ma10,
            'is_above_ma20': current_price > ma20,
            'is_prev_red': is_prev_red,
            'avg_volume': avg_volume,
        }
    except Exception as e:
        logger.error(f"获取 {code} 技术数据失败: {e}")
        return None


def analyze_sell_signal(
    code: str,
    name: str,
    buy_price: float,
    category: str,
    tech_data: Dict,
    highest_price: float
) -> Optional[Dict]:
    """
    分析卖出信号 (v2.3.1 增强版 - 含ATR止损)
    
    策略说明：
    1. ATR动态止损：根据波动率自动调整止损位
    2. 移动止盈：盈利后启动跟踪止损保护利润
    3. 分类策略：不同RPS分类使用不同阈值
    
    Returns:
        卖出信号字典，无信号返回None
    """
    current = tech_data['current_price']
    ma5 = tech_data['ma5']
    ma10 = tech_data['ma10']
    atr = tech_data.get('atr', 0)
    
    pnl_pct = (current - buy_price) / buy_price * 100
    drawdown = (current - highest_price) / highest_price * 100 if highest_price > buy_price else 0
    
    signal = None
    
    # =========================================
    # 1. ATR动态止损 (优先级最高)
    # =========================================
    try:
        from config import STOP_LOSS_STRATEGY
        stop_mode = STOP_LOSS_STRATEGY.get('mode', 'hybrid')
        atr_multiplier = STOP_LOSS_STRATEGY.get('atr_multiplier', 2.0)
        
        if stop_mode in ['atr', 'hybrid'] and atr > 0:
            # 计算ATR止损位
            atr_stop = buy_price - atr * atr_multiplier
            
            if current < atr_stop:
                signal = {
                    'type': 'STOP_LOSS',
                    'reason': f'触发ATR止损 (止损位={atr_stop:.2f}, 2倍ATR={atr*2:.2f})',
                    'suggestion': '根据波动率止损，避免更大损失'
                }
    except Exception:
        pass
    
    # =========================================
    # 2. 移动止盈 (Trailing Stop)
    # =========================================
    if signal is None:
        try:
            from config import STOP_LOSS_STRATEGY
            trailing_cfg = STOP_LOSS_STRATEGY.get('trailing_stop', {})
            
            if trailing_cfg.get('enabled', True):
                activation = trailing_cfg.get('activation_pct', 5.0)
                callback = trailing_cfg.get('callback_pct', 3.0)
                
                max_pnl = (highest_price - buy_price) / buy_price * 100
                
                # 如果曾经盈利超过激活点，且现在回撤超过回调点
                if max_pnl >= activation and drawdown < -callback:
                    signal = {
                        'type': 'TRAILING_STOP',
                        'reason': f'移动止盈触发 (最高盈利{max_pnl:.1f}%, 回撤{drawdown:.1f}%)',
                        'suggestion': f'利润回吐超{callback}%，锁定利润'
                    }
        except Exception:
            pass
    
    # =========================================
    # 3. 分类策略 (基于RPS分类)
    # =========================================
    if signal is None:
        if '趋势核心' in category:
            # 趋势核心: 跌破MA5止盈/止损
            if current < ma5 and pnl_pct > 0:
                signal = {
                    'type': 'TAKE_PROFIT',
                    'reason': f'跌破MA5止盈 (MA5={ma5:.2f})',
                    'suggestion': '趋势走弱，建议获利了结'
                }
            elif current < ma5 and pnl_pct < 0:
                signal = {
                    'type': 'STOP_LOSS',
                    'reason': f'跌破MA5止损 (MA5={ma5:.2f})',
                    'suggestion': '趋势破位，建议止损'
                }
            elif pnl_pct >= 10:
                signal = {
                    'type': 'TAKE_PROFIT',
                    'reason': f'涨幅达10%',
                    'suggestion': '可以考虑减仓锁定利润'
                }
        
        elif '潜力股' in category:
            # 潜力股: 涨5%止盈 或 跌破MA5止损
            if pnl_pct >= 5:
                signal = {
                    'type': 'TAKE_PROFIT',
                    'reason': f'涨幅达5%',
                    'suggestion': '潜力股，建议卖出一半'
                }
            elif current < ma5 and pnl_pct < -2:
                signal = {
                    'type': 'STOP_LOSS',
                    'reason': f'跌破MA5且亏损 (MA5={ma5:.2f})',
                    'suggestion': '走势转弱，建议离场'
                }
        
        else:  # 稳健标的
            # 稳健标的: 涨3%走 或 跌3%止损
            if pnl_pct >= 3:
                signal = {
                    'type': 'TAKE_PROFIT',
                    'reason': f'涨幅达3%',
                    'suggestion': '稳健标的，落袋为安'
                }
            elif pnl_pct <= -3:
                signal = {
                    'type': 'STOP_LOSS',
                    'reason': f'跌幅超3%',
                    'suggestion': '建议止损出局'
                }
    
    # =========================================
    # 4. 通用回撤保护 (兜底)
    # =========================================
    if signal is None and highest_price > buy_price:
        max_pnl = (highest_price - buy_price) / buy_price * 100
        if max_pnl > 5 and drawdown < -3:
            signal = {
                'type': 'DRAWDOWN',
                'reason': f'回撤保护 (最高浮盈{max_pnl:.1f}%，已回撤{drawdown:.1f}%)',
                'suggestion': '利润回吐，建议保护利润'
            }
    
    if signal:
        signal.update({
            'code': code,
            'name': name,
            'buy_price': buy_price,
            'current_price': current,
            'pnl_pct': pnl_pct,
            'category': category,
            'ma5': ma5,
            'ma10': ma10,
            'atr': atr,
        })
    
    return signal


def run_virtual_monitor() -> List[Dict]:
    """
    运行虚拟持仓监控
    
    Returns:
        卖出信号列表
    """
    positions = load_virtual_positions()
    
    if not positions:
        logger.info("📭 暂无虚拟持仓")
        return []
    
    # 过滤出未平仓的持仓
    active_positions = {k: v for k, v in positions.items() if not v.get('closed', False)}
    
    if not active_positions:
        logger.info("📭 所有虚拟持仓已平仓")
        return []
    
    logger.info(f"📡 监控 {len(active_positions)} 只虚拟持仓...")
    
    signals = []
    
    for code, info in active_positions.items():
        # 获取技术数据
        tech_data = get_stock_technical_data(code)
        if tech_data is None:
            continue
        
        current = tech_data['current_price']
        
        # 更新最高/最低价
        if current > info.get('highest_price', 0):
            positions[code]['highest_price'] = current
        if current < info.get('lowest_price', float('inf')):
            positions[code]['lowest_price'] = current
        
        # 分析卖出信号
        signal = analyze_sell_signal(
            code=code,
            name=info['name'],
            buy_price=info['buy_price'],
            category=info.get('category', ''),
            tech_data=tech_data,
            highest_price=positions[code]['highest_price']
        )
        
        if signal:
            signals.append(signal)
            
            # 自动平仓（虚拟）
            positions[code]['closed'] = True
            positions[code]['close_date'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            positions[code]['close_price'] = current
            positions[code]['close_reason'] = signal['reason']
            positions[code]['pnl_pct'] = signal['pnl_pct']
            
            # 记录到交易历史
            trades = load_virtual_trades()
            trades.append({
                'code': code,
                'name': info['name'],
                'buy_price': info['buy_price'],
                'buy_date': info['buy_date'],
                'sell_price': current,
                'sell_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'pnl_pct': round(signal['pnl_pct'], 2),
                'category': info.get('category', ''),
                'rps': info.get('rps', 0),
                'reason': signal['reason'],
                'type': signal['type'],
                'days_held': (datetime.now() - datetime.strptime(info['buy_date'], '%Y-%m-%d')).days,
            })
            save_virtual_trades(trades)
            
            logger.info(f"  📤 {code} {info['name']}: {signal['reason']} | 盈亏: {signal['pnl_pct']:+.2f}%")
    
    save_virtual_positions(positions)
    
    return signals


def format_virtual_signal_message(signals: List[Dict]) -> str:
    """格式化虚拟监控信号消息"""
    if not signals:
        return ""
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📅 监控时间: {now}\n"]
    
    profit_signals = [s for s in signals if s['type'] == 'TAKE_PROFIT']
    loss_signals = [s for s in signals if s['type'] == 'STOP_LOSS']
    drawdown_signals = [s for s in signals if s['type'] == 'DRAWDOWN']
    
    if profit_signals:
        lines.append("### 🎉 止盈信号\n")
        for s in profit_signals:
            lines.append(f"**{s['code']} {s['name']}** [{s['category']}]")
            lines.append(f"  买入: {s['buy_price']} → 现价: {s['current_price']:.2f}")
            lines.append(f"  盈亏: **{s['pnl_pct']:+.2f}%**")
            lines.append(f"  原因: {s['reason']}")
            lines.append(f"  👉 {s['suggestion']}")
            lines.append("")
    
    if loss_signals:
        lines.append("### ⚠️ 止损信号\n")
        for s in loss_signals:
            lines.append(f"**{s['code']} {s['name']}** [{s['category']}]")
            lines.append(f"  买入: {s['buy_price']} → 现价: {s['current_price']:.2f}")
            lines.append(f"  盈亏: **{s['pnl_pct']:+.2f}%**")
            lines.append(f"  原因: {s['reason']}")
            lines.append(f"  👉 {s['suggestion']}")
            lines.append("")
    
    if drawdown_signals:
        lines.append("### 📉 回撤信号\n")
        for s in drawdown_signals:
            lines.append(f"**{s['code']} {s['name']}** [{s['category']}]")
            lines.append(f"  买入: {s['buy_price']} → 现价: {s['current_price']:.2f}")
            lines.append(f"  盈亏: **{s['pnl_pct']:+.2f}%**")
            lines.append(f"  原因: {s['reason']}")
            lines.append(f"  👉 {s['suggestion']}")
            lines.append("")
    
    return "\n".join(lines)


def generate_statistics_report() -> Dict:
    """
    生成统计报告
    
    Returns:
        统计数据字典
    """
    trades = load_virtual_trades()
    
    if not trades:
        return {}
    
    df = pd.DataFrame(trades)
    
    # 整体统计
    total = len(df)
    wins = len(df[df['pnl_pct'] > 0])
    losses = len(df[df['pnl_pct'] < 0])
    
    stats = {
        'updated_at': datetime.now().isoformat(),
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': round(wins / total * 100, 1) if total > 0 else 0,
        'avg_pnl': round(df['pnl_pct'].mean(), 2),
        'avg_win': round(df[df['pnl_pct'] > 0]['pnl_pct'].mean(), 2) if wins > 0 else 0,
        'avg_loss': round(df[df['pnl_pct'] < 0]['pnl_pct'].mean(), 2) if losses > 0 else 0,
        'max_win': round(df['pnl_pct'].max(), 2),
        'max_loss': round(df['pnl_pct'].min(), 2),
        'avg_days_held': round(df['days_held'].mean(), 1),
        'by_category': {},
        'by_type': {},
    }
    
    # 按分类统计
    for category in df['category'].unique():
        cat_df = df[df['category'] == category]
        cat_wins = len(cat_df[cat_df['pnl_pct'] > 0])
        stats['by_category'][category] = {
            'count': len(cat_df),
            'win_rate': round(cat_wins / len(cat_df) * 100, 1) if len(cat_df) > 0 else 0,
            'avg_pnl': round(cat_df['pnl_pct'].mean(), 2),
        }
    
    # 按信号类型统计
    for sig_type in df['type'].unique():
        type_df = df[df['type'] == sig_type]
        stats['by_type'][sig_type] = {
            'count': len(type_df),
            'avg_pnl': round(type_df['pnl_pct'].mean(), 2),
        }
    
    return stats


def print_statistics_report():
    """打印统计报告"""
    stats = generate_statistics_report()
    
    if not stats:
        logger.info("📭 暂无虚拟交易记录")
        return
    
    logger.info("=" * 70)
    logger.info("📊 虚拟交易统计报告")
    logger.info(f"📅 更新时间: {stats['updated_at'][:19]}")
    logger.info("=" * 70)
    
    logger.info(f"\n📈 整体表现:")
    logger.info(f"   总交易数: {stats['total_trades']}")
    logger.info(f"   胜率: {stats['win_rate']}% ({stats['wins']}胜 / {stats['losses']}负)")
    logger.info(f"   平均收益: {stats['avg_pnl']:+.2f}%")
    logger.info(f"   平均盈利: {stats['avg_win']:+.2f}% | 平均亏损: {stats['avg_loss']:+.2f}%")
    logger.info(f"   最大盈利: {stats['max_win']:+.2f}% | 最大亏损: {stats['max_loss']:+.2f}%")
    logger.info(f"   平均持仓: {stats['avg_days_held']} 天")
    
    logger.info(f"\n📋 分类表现:")
    for category, data in stats['by_category'].items():
        emoji = "🟢" if data['avg_pnl'] > 0 else "🔴"
        logger.info(f"   {category}: {emoji} 胜率 {data['win_rate']}% | 平均 {data['avg_pnl']:+.2f}% ({data['count']}笔)")
    
    logger.info(f"\n📊 信号类型:")
    for sig_type, data in stats['by_type'].items():
        logger.info(f"   {sig_type}: {data['count']}笔 | 平均 {data['avg_pnl']:+.2f}%")
    
    logger.info("\n" + "=" * 70)


def list_virtual_positions():
    """列出虚拟持仓"""
    positions = load_virtual_positions()
    
    active = {k: v for k, v in positions.items() if not v.get('closed', False)}
    closed = {k: v for k, v in positions.items() if v.get('closed', False)}
    
    logger.info(f"\n📋 虚拟持仓状态:")
    logger.info(f"   活跃: {len(active)} 只 | 已平仓: {len(closed)} 只")
    
    if active:
        logger.info(f"\n🔵 活跃持仓:")
        for code, info in active.items():
            logger.info(f"   {code} {info['name']} | 买入: {info['buy_price']} ({info['buy_date']}) | {info['category']}")
    
    if closed:
        logger.info(f"\n⚪ 近期平仓:")
        recent_closed = sorted(closed.items(), key=lambda x: x[1].get('close_date', ''), reverse=True)[:5]
        for code, info in recent_closed:
            pnl = info.get('pnl_pct', 0)
            emoji = "🟢" if pnl > 0 else "🔴"
            logger.info(f"   {code} {info['name']} | {emoji} {pnl:+.2f}% | {info.get('close_reason', '')}")


def clear_virtual_positions():
    """清空虚拟持仓"""
    save_virtual_positions({})
    logger.info("🧹 已清空虚拟持仓")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='虚拟持仓追踪')
    parser.add_argument('--monitor', action='store_true', help='运行监控')
    parser.add_argument('--list', action='store_true', help='列出持仓')
    parser.add_argument('--stats', action='store_true', help='查看统计')
    parser.add_argument('--clear', action='store_true', help='清空持仓')
    
    args = parser.parse_args()
    
    if args.clear:
        clear_virtual_positions()
    elif args.list:
        list_virtual_positions()
    elif args.stats:
        print_statistics_report()
    else:
        run_virtual_monitor()

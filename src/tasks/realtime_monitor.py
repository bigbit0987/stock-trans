#!/usr/bin/env python
"""
盘中实时监控模块 (Realtime Monitor) v2.4.1
功能：
1. 盘中实时监控持仓股票价格
2. 达到止盈/止损点时发送钉钉提醒
3. 智能冷却机制，避免频繁骚扰

v2.4.1 改进：
- 使用线程安全的 JSON 读写，避免多进程并发时数据损坏
"""
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from config import REALTIME_MONITOR
from src.utils import logger
from src.database import db
from src.indicators import get_grade_based_stop_params


# 提醒记录文件 (用于冷却机制)
ALERT_HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "alert_history.json")


def load_alert_history() -> Dict:
    """加载提醒历史记录 (线程安全)"""
    return safe_read_json(ALERT_HISTORY_FILE, default={})


def save_alert_history(history: Dict):
    """保存提醒历史记录 (线程安全 + 原子写入)"""
    safe_write_json(ALERT_HISTORY_FILE, history)


def can_send_alert(code: str, alert_type: str) -> bool:
    """
    检查是否可以发送提醒 (冷却机制)
    
    Args:
        code: 股票代码
        alert_type: 提醒类型 (如 'profit_3', 'stop_loss', 'drawdown')
    
    Returns:
        是否可以发送
    """
    history = load_alert_history()
    key = f"{code}_{alert_type}"
    
    if key not in history:
        return True
    
    last_time = datetime.fromisoformat(history[key])
    cooldown = REALTIME_MONITOR['alert_cooldown']
    
    return (datetime.now() - last_time).total_seconds() > cooldown


def record_alert(code: str, alert_type: str):
    """记录提醒时间"""
    history = load_alert_history()
    key = f"{code}_{alert_type}"
    history[key] = datetime.now().isoformat()
    save_alert_history(history)


def is_trading_time() -> bool:
    """判断当前是否在交易时间内"""
    now = datetime.now()
    
    # 周末不交易
    if now.weekday() >= 5:
        return False
    
    current_time = now.strftime('%H:%M')
    
    trading_start = REALTIME_MONITOR['trading_start']
    trading_end = REALTIME_MONITOR['trading_end']
    lunch_start = REALTIME_MONITOR['lunch_start']
    lunch_end = REALTIME_MONITOR['lunch_end']
    
    # 上午交易时段
    if trading_start <= current_time < lunch_start:
        return True
    
    # 下午交易时段
    if lunch_end <= current_time < trading_end:
        return True
    
    return False


def get_realtime_prices(codes: List[str]) -> Dict[str, float]:
    """
    批量获取实时价格
    
    Args:
        codes: 股票代码列表
    
    Returns:
        {代码: 当前价格}
    """
    try:
        df = ak.stock_zh_a_spot_em()
        prices = {}
        for code in codes:
            stock = df[df['代码'] == code]
            if not stock.empty:
                prices[code] = stock.iloc[0]['最新价']
        return prices
    except Exception as e:
        logger.error(f"获取实时价格失败: {e}")
        return {}


def analyze_position(
    code: str,
    name: str,
    buy_price: float,
    current_price: float,
    highest_price: float,
    strategy: str
) -> List[Dict]:
    """
    分析单只股票，生成预警信号
    
    Returns:
        预警列表
    """
    alerts = []
    
    # 计算涨跌幅
    pnl_pct = (current_price - buy_price) / buy_price * 100
    
    # v2.5.0: 根据 Grade 获取差异化参数
    grade = kwargs.get('grade', 'B')
    risk_params = get_grade_based_stop_params(grade)
    
    # 计算回撤
    drawdown = (current_price - highest_price) / highest_price * 100 if highest_price > 0 else 0
    
    # 1. 检查止盈点
    for level in REALTIME_MONITOR['take_profit_levels']:
        if pnl_pct >= level:
            alert_type = f"profit_{level}"
            if can_send_alert(code, alert_type):
                alerts.append({
                    'code': code,
                    'name': name,
                    'type': 'TAKE_PROFIT',
                    'alert_type': alert_type,
                    'current': current_price,
                    'buy_price': buy_price,
                    'pnl_pct': pnl_pct,
                    'level': level,
                    'strategy': strategy,
                    'message': f"🎉 涨幅达 {level}%! 当前 {pnl_pct:.2f}%"
                })
                break  # 只提醒最高的止盈点
    
    # 2. 检查止损点
    stop_loss = REALTIME_MONITOR['stop_loss_level']
    if pnl_pct <= stop_loss:
        alert_type = "stop_loss"
        if can_send_alert(code, alert_type):
            alerts.append({
                'code': code,
                'name': name,
                'type': 'STOP_LOSS',
                'alert_type': alert_type,
                'current': current_price,
                'buy_price': buy_price,
                'pnl_pct': pnl_pct,
                'level': stop_loss,
                'strategy': strategy,
                'message': f"⚠️ 跌破止损线! 当前 {pnl_pct:.2f}%"
            })
    
    # 3. 检查回撤 (只对有浮盈的股票)
    if highest_price > buy_price:
        max_pnl = (highest_price - buy_price) / buy_price * 100
        # v2.5.0: 使用差异化回撤阈值
        drawdown_alert = risk_params.get('drawdown_threshold', -3.0)
        min_profit_for_drawdown = REALTIME_MONITOR.get('drawdown_monitor_min_profit', 3)
        
        if drawdown <= drawdown_alert and max_pnl > min_profit_for_drawdown:
            alert_type = "drawdown"
            if can_send_alert(code, alert_type):
                alerts.append({
                    'code': code,
                    'name': name,
                    'type': 'DRAWDOWN',
                    'alert_type': alert_type,
                    'current': current_price,
                    'buy_price': buy_price,
                    'highest': highest_price,
                    'pnl_pct': pnl_pct,
                    'max_pnl': max_pnl,
                    'drawdown': drawdown,
                    'strategy': strategy,
                    'message': f"📉 回撤预警! 最高浮盈 {max_pnl:.1f}% 已回撤 {drawdown:.1f}%"
                })
    
    return alerts


def run_monitor_once() -> List[Dict]:
    """
    执行一次监控检查
    
    Returns:
        本次检查产生的所有预警
    """
    from src.tasks.portfolio import load_holdings
    
    holdings = load_holdings()
    
    if not holdings:
        return []
    
    # 批量获取价格
    codes = list(holdings.keys())
    prices = get_realtime_prices(codes)
    
    all_alerts = []
    
    for code, info in holdings.items():
        if code not in prices:
            continue
        
        current_price = prices[code]
        
        # ---【v2.5.0: 更新最高价并持久化到数据库】---
        old_highest = info.get('highest_price', info['buy_price'])
        if current_price > old_highest:
            info['highest_price'] = current_price
            db.save_holding(code, info) # 立即同步数据库，防碰撞且保证连续性
            highest = current_price
        else:
            highest = old_highest
            
        alerts = analyze_position(
            code=code,
            name=info['name'],
            buy_price=info['buy_price'],
            current_price=current_price,
            highest_price=highest,
            strategy=info.get('strategy', 'STABLE'),
            grade=info.get('grade', 'B') # 传入评级
        )
        
        all_alerts.extend(alerts)
    
    return all_alerts


def format_monitor_alert(alerts: List[Dict]) -> str:
    """格式化监控预警消息"""
    if not alerts:
        return ""
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📅 监控时间: {now}\n"]
    
    # 按类型分组
    profit_alerts = [a for a in alerts if a['type'] == 'TAKE_PROFIT']
    loss_alerts = [a for a in alerts if a['type'] == 'STOP_LOSS']
    drawdown_alerts = [a for a in alerts if a['type'] == 'DRAWDOWN']
    
    if profit_alerts:
        lines.append("### 🎉 止盈提醒\n")
        for a in profit_alerts:
            lines.append(f"**{a['code']} {a['name']}**")
            lines.append(f"  买入: {a['buy_price']} → 现价: {a['current']:.2f}")
            lines.append(f"  {a['message']}")
            # 根据策略给出建议
            if a['strategy'] == 'RPS_CORE':
                lines.append(f"  👉 趋势核心股，可继续持有观察")
            elif a['strategy'] == 'POTENTIAL':
                lines.append(f"  👉 潜力股，建议卖出一半锁定利润")
            else:
                lines.append(f"  👉 稳健标的，建议落袋为安")
            lines.append("")
    
    if loss_alerts:
        lines.append("### ⚠️ 止损预警\n")
        for a in loss_alerts:
            lines.append(f"**{a['code']} {a['name']}**")
            lines.append(f"  买入: {a['buy_price']} → 现价: {a['current']:.2f}")
            lines.append(f"  {a['message']}")
            lines.append(f"  👉 建议考虑止损出局")
            lines.append("")
    
    if drawdown_alerts:
        lines.append("### 📉 回撤预警\n")
        for a in drawdown_alerts:
            lines.append(f"**{a['code']} {a['name']}**")
            lines.append(f"  买入: {a['buy_price']} → 最高: {a['highest']:.2f} → 现价: {a['current']:.2f}")
            lines.append(f"  {a['message']}")
            lines.append(f"  👉 注意保护利润，考虑止盈")
            lines.append("")
    
    return "\n".join(lines)


def run_realtime_monitor(duration_minutes: int = None, silent: bool = False):
    """
    运行实时监控
    
    Args:
        duration_minutes: 监控时长(分钟)，None表示持续到收盘
        silent: 是否静默模式(不打印日志)
    """
    from src.notifier import notify_all
    
    if not silent:
        logger.info("=" * 60)
        logger.info("📡 盘中实时监控已启动")
        logger.info(f"⏰ 检查间隔: {REALTIME_MONITOR['check_interval']} 秒")
        logger.info(f"🎯 止盈点: {REALTIME_MONITOR['take_profit_levels']}%")
        logger.info(f"🛡️ 止损点: {REALTIME_MONITOR['stop_loss_level']}%")
        logger.info("=" * 60)
    
    start_time = datetime.now()
    check_count = 0
    alert_count = 0
    
    try:
        while True:
            # 检查是否超时
            if duration_minutes:
                elapsed = (datetime.now() - start_time).total_seconds() / 60
                if elapsed >= duration_minutes:
                    logger.info(f"\n⏱️ 监控时长已到 ({duration_minutes} 分钟)")
                    break
            
            # 检查是否在交易时间
            if not is_trading_time():
                if not silent:
                    logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] ⏸️ 非交易时间，等待中...")
                time.sleep(60)  # 非交易时间每分钟检查一次
                continue
            
            # 执行监控检查
            check_count += 1
            if not silent:
                logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 第 {check_count} 次检查...")
            
            alerts = run_monitor_once()
            
            if alerts:
                alert_count += len(alerts)
                
                # 记录提醒
                for alert in alerts:
                    record_alert(alert['code'], alert['alert_type'])
                
                # 发送钉钉通知
                message = format_monitor_alert(alerts)
                notify_all("📡 盘中监控预警", message)
                
                if not silent:
                    logger.info(f"   📱 发送了 {len(alerts)} 条预警")
            else:
                if not silent:
                    logger.info(f"   ✅ 一切正常")
            
            # 等待下一次检查
            time.sleep(REALTIME_MONITOR['check_interval'])
            
    except KeyboardInterrupt:
        logger.info("\n⏹️ 监控已手动停止")
    
    # 统计
    logger.info("=" * 60)
    logger.info("📊 监控统计")
    logger.info(f"   检查次数: {check_count}")
    logger.info(f"   发送预警: {alert_count}")
    logger.info("=" * 60)


def run_monitor_check():
    """
    执行单次监控检查 (供定时任务调用)
    不会持续运行，只检查一次
    """
    from src.notifier import notify_all
    
    if not is_trading_time():
        logger.info("⏸️ 非交易时间，跳过监控")
        return []
    
    logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 执行监控检查...")
    
    alerts = run_monitor_once()
    
    if alerts:
        for alert in alerts:
            record_alert(alert['code'], alert['alert_type'])
        
        message = format_monitor_alert(alerts)
        notify_all("📡 盘中监控预警", message)
        logger.info(f"📱 发送了 {len(alerts)} 条预警")
    else:
        logger.info("✅ 持仓状态正常")
    
    return alerts


def clear_alert_history():
    """清理过期的提醒历史 (保留24小时内的)"""
    history = load_alert_history()
    cutoff = datetime.now() - timedelta(hours=24)
    
    new_history = {}
    for key, time_str in history.items():
        try:
            alert_time = datetime.fromisoformat(time_str)
            if alert_time > cutoff:
                new_history[key] = time_str
        except ValueError:
            pass
    
    save_alert_history(new_history)
    logger.info(f"🧹 清理了 {len(history) - len(new_history)} 条过期提醒记录")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='盘中实时监控')
    parser.add_argument('--once', action='store_true', help='只检查一次')
    parser.add_argument('--duration', type=int, help='监控时长(分钟)')
    parser.add_argument('--clear', action='store_true', help='清理提醒历史')
    
    args = parser.parse_args()
    
    if args.clear:
        clear_alert_history()
    elif args.once:
        run_monitor_check()
    else:
        run_realtime_monitor(duration_minutes=args.duration)

#!/usr/bin/env python
"""
持仓管理任务 (Portfolio Manager) v2.4.1
功能：
1. 记录持仓
2. 每日巡检（监控止损位）
3. 风险提醒

v2.4.1 改进：
- 使用线程安全的 JSON 读写，避免多进程并发时数据损坏
- 增加 ATR 止损位计算和存储
"""
import os
import sys
import datetime
import pandas as pd

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config import RESULTS_DIR, PORTFOLIO_CHECK
from src.utils import logger
from src.database import db



def load_holdings() -> dict:
    """从 SQLite 加载持仓数据 (v2.5.0)"""
    return db.get_holdings()


def save_holdings(holdings: dict):
    """保存持仓数据到 SQLite (v2.5.0)"""
    # 1. 保存到数据库
    old_holdings = db.get_holdings()
    old_codes = set(old_holdings.keys())
    new_codes = set(holdings.keys())
    
    # 移除已平仓的 (在旧的里但不在新的里)
    for code in old_codes - new_codes:
        db.remove_holding(code)
    
    # 保存/更新现有的
    for code, info in holdings.items():
        db.save_holding(code, info)
    
    # 2. 自动备份数据库 (每天只备份一次)
    today = datetime.date.today().strftime('%Y%m%d')
    backup_marker = os.path.join(BACKUP_DIR, f".db_backup_{today}")
    if not os.path.exists(backup_marker):
        backup_data()
        # 创建备份标记文件
        os.makedirs(BACKUP_DIR, exist_ok=True)
        with open(backup_marker, 'w') as f:
            f.write(datetime.datetime.now().isoformat())


# 备份目录
BACKUP_DIR = os.path.join(PROJECT_ROOT, "data", "backup")


def backup_data():
    """备份数据库文件 (v2.5.0)"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    today = datetime.date.today().strftime('%Y%m%d')
    
    import shutil
    from src.database import DB_PATH
    
    # 备份数据库主文件
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, f"alphahunter_{today}.db"))
    
    # 只保留最近30天的备份 (.db 文件)
    try:
        files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')]
        files.sort()
        while len(files) > 30:
            os.remove(os.path.join(BACKUP_DIR, files.pop(0)))
    except Exception:
        pass


def add_position(
    code: str, 
    name: str, 
    buy_price: float, 
    quantity: int = 0,
    strategy: str = "STABLE",
    note: str = ""
):
    """
    添加持仓 (支持加仓合并) v2.4.1 增强版
    
    Args:
        code: 股票代码
        name: 股票名称
        buy_price: 买入价格
        quantity: 买入数量
        strategy: 策略类型 (RPS_CORE=趋势核心, POTENTIAL=潜力股, STABLE=稳健标的)
        note: 备注
    
    v2.4.1 新增:
        - 自动计算 ATR 并存储动态止损位
    """
    from src.data_loader import get_stock_history
    from src.indicators import calculate_atr, calculate_atr_stop_loss
    from config import STOP_LOSS_STRATEGY
    
    holdings = load_holdings()
    
    if code in holdings:
        # ---【加仓合并逻辑】---
        old_info = holdings[code]
        old_qty = old_info.get('quantity', 0)
        old_price = old_info.get('buy_price', 0)
        
        # 计算加权平均成本
        total_qty = old_qty + quantity
        if total_qty > 0 and old_qty > 0:
            new_price = (old_price * old_qty + buy_price * quantity) / total_qty
        else:
            new_price = buy_price
            total_qty = max(total_qty, quantity)
        
        # 更新持仓信息
        holdings[code].update({
            "buy_price": round(new_price, 3),  # 更新成本
            "quantity": total_qty,              # 累加数量
            "highest_price": max(old_info.get('highest_price', 0), buy_price), # 维持/更新最高价
            "note": f"{old_info.get('note', '')} | 加仓@{buy_price}" if note == '' else note
        })
        # 策略类型不更新，保持原来的
        # 买入日期不更新，保留最早日期
        
        # v2.4.1: 加仓时重新计算 ATR 止损位
        atr_stop = _calculate_atr_stop_for_stock(code, new_price)
        if atr_stop:
            holdings[code]['atr_stop'] = atr_stop
        
        save_holdings(holdings)
        logger.info(f"🔄 已合并持仓: {code} {name}")
        logger.info(f"   新成本: {new_price:.3f} | 数量: {total_qty}")
    else:
        # 新开仓
        # v2.5.0: 增加等级映射 (策略 -> 等级)
        # RPS_CORE=A, POTENTIAL=B, STABLE=C
        grade_map = {"RPS_CORE": "A", "POTENTIAL": "B", "STABLE": "C"}
        grade = grade_map.get(strategy, "B")
        
        # v2.5.0: 计算 ATR 止损位 (传入 grade 以实现差异化止损)
        atr_stop = _calculate_atr_stop_for_stock(code, buy_price, grade)
        
        holdings[code] = {
            "name": name,
            "buy_price": buy_price,
            "highest_price": buy_price,
            "buy_date": datetime.date.today().strftime("%Y-%m-%d"),
            "quantity": quantity,
            "strategy": strategy,
            "grade": grade,    # v2.5.0: 存储评级
            "note": note,
            "atr_stop": atr_stop  # v2.4.1: 动态 ATR 止损位
        }
        save_holdings(holdings)
        logger.info(f"✅ 已添加持仓: {code} {name} @ {buy_price}")
        if atr_stop:
            logger.info(f"   📊 ATR 动态止损位: {atr_stop:.2f}")


def _calculate_atr_stop_for_stock(code: str, buy_price: float, grade: str = 'B') -> float:
    """
    为股票计算 ATR 止损位 (内部函数)
    v2.5.0: 解耦至 src.indicators 并支持差异化评级
    
    Returns:
        ATR 止损价位，计算失败时返回 None
    """
    try:
        from src.data_loader import get_stock_history
        from src.indicators import calculate_atr, calculate_atr_stop_loss, get_grade_based_stop_params
        from config import STOP_LOSS_STRATEGY
        
        # 获取等级对应的参数
        risk_params = get_grade_based_stop_params(grade)
        
        # 获取历史数据计算 ATR
        hist = get_stock_history(code, 30)
        if hist is not None and len(hist) >= 14:
            atr = calculate_atr(
                hist['最高'].tolist(),
                hist['最低'].tolist(),
                hist['收盘'].tolist(),
                period=STOP_LOSS_STRATEGY.get('atr_period', 14)
            )
            if atr > 0:
                multiplier = risk_params.get('atr_multiplier', 1.5)
                return calculate_atr_stop_loss(buy_price, atr, multiplier)
        
        # 计算失败时使用固定止损 (同样参考风险等级，A级宽一些)
        fixed_pct = -5.0 if grade == 'A' else -3.0
        return round(buy_price * (1 + fixed_pct / 100), 2)
        
    except Exception as e:
        logger.warning(f"计算 {code} ATR 止损失败: {e}")
        return None





def get_latest_results_file() -> str:
    """
    获取 output/results 目录下最新的选股结果 CSV 文件
    解决周一导入找不到文件的问题
    """
    if not os.path.exists(RESULTS_DIR):
        return None
    
    # 获取所有以 '选股结果_' 开头的文件
    files = [f for f in os.listdir(RESULTS_DIR) 
             if f.startswith('选股结果_') and f.endswith('.csv')]
    
    if not files:
        return None
    
    # 按文件名排序（因为文件名包含日期，排序后最后一个就是最新的）
    files.sort()
    return os.path.join(RESULTS_DIR, files[-1])


def close_position(code: str, sell_price: float = None, sell_quantity: int = 0, force: bool = False):
    """
    平仓并归档交易记录 (支持减仓)
    
    Args:
        code: 股票代码
        sell_price: 卖出价格（不传则获取当前价）
        sell_quantity: 卖出数量，0 表示全部卖出
        force: 强制卖出（跳过T+1检查，用于做T等特殊情况）
    """
    holdings = load_holdings()
    
    if code not in holdings:
        logger.warning(f"⚠️ 未找到持仓: {code}")
        return
    
    info = holdings[code]
    total_qty = info.get('quantity', 0)
    
    # ---【T+1 限制检查】---
    buy_date_str = info['buy_date']
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    if buy_date_str == today_str and not force:
        logger.error(f"❌ 拒绝卖出: {code} {info['name']}")
        logger.info(f"   该股票是今日({today_str})买入的持仓 (A股T+1限制)")
        logger.info(f"   如果确实需要卖出(如做T)，请使用: --close {code},{sell_price or '价格'},数量,force")
        return
    # -----------------------
    
    # 如果没有传卖出价，获取当前价
    if sell_price is None:
        try:
            df = ak.stock_zh_a_spot_em()
            stock = df[df['代码'] == code]
            if not stock.empty:
                sell_price = stock.iloc[0]['最新价']
            else:
                logger.error(f"❌ 无法获取 {code} 当前价格，请手动指定卖出价")
                return
        except Exception:
            logger.error(f"❌ 无法获取 {code} 当前价格，请手动指定卖出价")
            return
    
    # 判断是全部卖出还是部分卖出
    is_sell_all = (sell_quantity == 0) or (total_qty == 0) or (sell_quantity >= total_qty)
    actual_sell_qty = total_qty if is_sell_all else sell_quantity
    
    # 计算盈亏
    buy_price = info['buy_price']
    pnl = (sell_price - buy_price) / buy_price * 100
    pnl_amount = (sell_price - buy_price) * actual_sell_qty
    
    # 计算持仓天数
    buy_date = datetime.datetime.strptime(info['buy_date'], '%Y-%m-%d').date()
    days_held = (datetime.date.today() - buy_date).days
    
    # 写入归档 CSV
    archive_file = os.path.join(PROJECT_ROOT, "data", "trade_history.csv")
    
    # 检查是否需要写入表头
    write_header = not os.path.exists(archive_file)
    
    import csv
    with open(archive_file, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['代码', '名称', '买入价', '卖出价', '盈亏%', '卖出数量',
                            '持仓天数', '策略', '买入日期', '卖出日期', '备注'])
        writer.writerow([
            code,
            info['name'],
            buy_price,
            sell_price,
            f"{pnl:.2f}",
            actual_sell_qty,
            days_held,
            info.get('strategy', 'STABLE'),
            info['buy_date'],
            datetime.date.today().strftime('%Y-%m-%d'),
            '减仓' if not is_sell_all else '清仓'
        ])
    
    # 更新或删除持仓
    if is_sell_all:
        del holdings[code]
        action = "💰 全部清仓"
    else:
        holdings[code]['quantity'] -= actual_sell_qty
        action = f"💰 减仓 {actual_sell_qty} 股 (剩余 {holdings[code]['quantity']} 股)"
    
    save_holdings(holdings)
    
    # v2.5.0: 归档到数据库交易历史
    db.add_trade_history({
        "code": code,
        "name": info['name'],
        "buy_date": info['buy_date'],
        "sell_date": datetime.date.today().strftime("%Y-%m-%d"),
        "buy_price": info['buy_price'],
        "sell_price": sell_price,
        "quantity": actual_sell_qty,
        "pnl_amount": pnl_amount,
        "pnl_pct": pnl,
        "strategy": info.get('strategy'),
        "grade": info.get('grade'),
        "note": '减仓' if not is_sell_all else '清仓'
    })
    
    # 显示结果
    if pnl >= 0:
        logger.info(f"{action}: {code} {info['name']}")
        logger.info(f"   买入: {buy_price} → 卖出: {sell_price}")
        logger.info(f"   盈利: {pnl:+.2f}% (持有{days_held}天)")
    else:
        logger.info(f"📉 {action}: {code} {info['name']}")
        logger.info(f"   买入: {buy_price} → 卖出: {sell_price}")
        logger.info(f"   亏损: {pnl:.2f}% (持有{days_held}天)")
    
    logger.info(f"   📝 已归档到: data/trade_history.csv")


def get_stock_ma5(code: str) -> tuple:
    """
    获取股票当前价格和 MA5
    
    Returns:
        (当前价, MA5, 是否跌破MA5)
    """
    try:
        # 获取实时价格
        df = ak.stock_zh_a_spot_em()
        stock = df[df['代码'] == code]
        if stock.empty:
            return None, None, None
        
        current_price = stock.iloc[0]['最新价']
        
        # 获取历史数据计算 MA5
        hist = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        
        # ---【日期安全检查】防止收盘后数据双重计算---
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        hist['日期_str'] = pd.to_datetime(hist['日期']).dt.strftime('%Y-%m-%d')
        if not hist.empty and hist.iloc[-1]['日期_str'] == today_str:
            # 如果最后一行是今天，切掉它！
            hist = hist.iloc[:-1]
        # -----------------------------------------
        
        if len(hist) < 4:  # 至少需要4天历史
            return current_price, None, None
        
        # 计算实时 MA5: (前4天收盘价 + 当前价) / 5
        closes = hist['收盘'].tail(4).tolist()
        ma5 = (sum(closes) + current_price) / 5
        
        is_below_ma5 = current_price < ma5
        
        return current_price, ma5, is_below_ma5
        
    except Exception as e:
        logger.error(f"   获取 {code} 数据出错: {e}")
        return None, None, None


def daily_check():
    """
    每日持仓巡检
    检查是否跌破止损位
    """
    logger.info("=" * 60)
    logger.info("📋 持仓巡检")
    logger.info(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    holdings = load_holdings()
    
    if not holdings:
        logger.info("\n📭 当前无持仓")
        return []
    
    logger.info(f"\n当前持仓: {len(holdings)} 只\n")
    
    alerts = []
    needs_save = False
    
    for code, info in holdings.items():
        name = info['name']
        buy_price = info['buy_price']
        buy_date = info['buy_date']
        strategy = info.get('strategy', 'STABLE')
        
        # 获取实时数据
        current, ma5, below_ma5 = get_stock_ma5(code)
        
        if current is None:
            logger.warning(f"  ⚠️ {code} {name}: 数据获取失败")
            continue
        
        # ---【更新持仓期间最高价】---
        highest = info.get('highest_price', buy_price)
        if current > highest:
            highest = current
            holdings[code]['highest_price'] = highest
            needs_save = True
            
        # 计算 历史最高盈亏比例
        max_pnl = (highest - buy_price) / buy_price * 100
        pnl = (current - buy_price) / buy_price * 100
        drawdown = (current - highest) / highest * 100 if highest > 0 else 0
        pnl_str = f"{pnl:+.2f}%"
        
        # 持仓天数
        days_held = (datetime.date.today() - datetime.datetime.strptime(buy_date, "%Y-%m-%d").date()).days
        
        # v2.4.1: 获取 ATR 止损位
        atr_stop = info.get('atr_stop')
        below_atr_stop = atr_stop and current < atr_stop
        
        # 状态判定
        status = "✅"
        action = ""
        
        # v2.4.1: ATR 止损优先检查
        if below_atr_stop:
            status = "🔴"
            action = f"🚨 跌破ATR止损位！(止损价: {atr_stop:.2f})"
            alerts.append({
                'code': code,
                'name': name,
                'current': current,
                'ma5': ma5,
                'pnl': pnl,
                'atr_stop': atr_stop,
                'action': f'跌破ATR止损位({atr_stop:.2f})，建议立即止损'
            })
        elif below_ma5:
            status = "🔴"
            action = "⚠️ 跌破MA5！"
            
            # 趋势核心股跌破MA5需要止盈/止损
            if strategy == "RPS_CORE":
                action = "🚨 止盈/止损信号！(跌破5日线)"
                alerts.append({
                    'code': code,
                    'name': name,
                    'current': current,
                    'ma5': ma5,
                    'pnl': pnl,
                    'action': '跌破5日线，建议离场'
                })
        else:
            # 只有在没有触发止损的情况下，才检查其他状态
            # v2.5.0: 根据评级动态获取阈值
            from src.indicators import get_grade_based_stop_params
            grade = info.get('grade', 'B')
            risk_params = get_grade_based_stop_params(grade)
            
            # 策略师建议：Grade A 容忍度更高，Grade C 更敏感
            drawdown_threshold = risk_params['drawdown_threshold']
            take_profit_alert = risk_params['take_profit']
            loss_attention = -5.0
            
            if max_pnl > 10 and drawdown < drawdown_threshold:
                # 收益回撤判定
                status = "🚨"
                action = f"📉 回撤止盈警报！({grade}级, 最高浮盈 {max_pnl:.1f}% 后回撤 {drawdown:.1f}%)"
                alerts.append({
                    'code': code,
                    'name': name,
                    'current': current,
                    'ma5': ma5,
                    'pnl': pnl,
                    'action': action
                })
            elif pnl > take_profit_alert:
                # 当前还在高位，报喜
                status = "🟢"
                action = f"💰 止盈提醒！收益超 {take_profit_alert}%"
                alerts.append({
                    'code': code,
                    'name': name,
                    'current': current,
                    'ma5': ma5,
                    'pnl': pnl,
                    'action': action
                })
            elif pnl < loss_attention:
                status = "🟡"
                action = "注意亏损"
        
        logger.info(f"  {status} {code} {name}")
        logger.info(f"     买入: {buy_price} ({buy_date}, 持有{days_held}天)")
        ma5_str = f"{ma5:.3f}" if ma5 else "N/A"
        atr_stop_str = f" | ATR止损: {atr_stop:.2f}" if atr_stop else ""
        logger.info(f"     现价: {current:.2f} | 最高: {highest:.2f} | 盈亏: {pnl_str} (回撤: {drawdown:.1f}%){atr_stop_str}")
        if action:
            logger.info(f"     👉 {action}")
        logger.info("")
    
    # 如果更新了最高价，保存持仓文件
    if needs_save:
        save_holdings(holdings)
    if alerts:
        logger.info("=" * 60)
        logger.info("🚨 需要立即关注的持仓:")
        logger.info("=" * 60)
        for alert in alerts:
            logger.info(f"  ❗ {alert['code']} {alert['name']}: {alert['action']}")
            if 'atr_stop' in alert:
                logger.info(f"     现价: {alert['current']:.2f} < ATR止损位: {alert['atr_stop']:.2f}")
            else:
                logger.info(f"     现价: {alert['current']:.2f} < MA5: {alert['ma5']:.2f}")
        logger.info("\n💡 建议: RPS_CORE 策略股票跌破5日线应止损出局！")
    
    return alerts


def list_holdings():
    """列出所有持仓"""
    holdings = load_holdings()
    
    if not holdings:
        logger.info("📭 当前无持仓")
        return
    
    logger.info("\n📋 当前持仓:")
    logger.info("-" * 60)
    logger.info(f"{'代码':<10} {'名称':<10} {'买入价':>8} {'日期':<12} {'策略':<12}")
    logger.info("-" * 60)
    
    for code, info in holdings.items():
        logger.info(f"{code:<10} {info['name']:<10} {info['buy_price']:>8.2f} {info['buy_date']:<12} {info.get('strategy', 'STABLE'):<12}")


def import_from_csv(csv_path: str = None, strategy: str = "STABLE"):
    """
    从选股结果 CSV 导入持仓
    """
    if csv_path is None:
        csv_path = get_latest_results_file()
        if csv_path:
            logger.info(f"📄 自动定位到最新文件: {os.path.basename(csv_path)}")
    
    if not csv_path or not os.path.exists(csv_path):
        logger.error(f"❌ 未找到选股结果文件")
        logger.info(f"   请先运行 scan.py 生成选股结果")
        return
    
    df = pd.read_csv(csv_path)
    
    logger.info(f"\n📥 从 {os.path.basename(csv_path)} 导入持仓:")
    logger.info("-" * 50)
    
    for _, row in df.iterrows():
        code = str(row['代码']).zfill(6)
        name = row['名称']
        price = row['现价']
        
        category = row.get('分类', '')
        if '趋势核心' in category:
            strat = 'RPS_CORE'
        elif '潜力股' in category:
            strat = 'POTENTIAL'
        else:
            strat = 'STABLE'
        
        logger.info(f"  {code} {name} @ {price} [{strat}]")
        add_position(code, name, price, strategy=strat)
    
    logger.info(f"\n✅ 已导入 {len(df)} 只股票")


if __name__ == "__main__":
    # 保留 CLI 兼容性，但建议通过 main.py 运行
    daily_check()

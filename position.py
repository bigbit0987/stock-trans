#!/usr/bin/env python
"""
持仓管理模块 (Position Manager)
功能：
1. 记录持仓
2. 每日巡检（监控止损位）
3. 风险提醒
"""
import os
import sys
import json
import datetime
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
from config import RESULTS_DIR

# 持仓文件路径
HOLDINGS_FILE = os.path.join(PROJECT_ROOT, "data", "holdings.json")


def load_holdings() -> dict:
    """加载持仓数据"""
    if os.path.exists(HOLDINGS_FILE):
        with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_holdings(holdings: dict):
    """保存持仓数据"""
    os.makedirs(os.path.dirname(HOLDINGS_FILE), exist_ok=True)
    with open(HOLDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)


def add_position(
    code: str, 
    name: str, 
    buy_price: float, 
    quantity: int = 0,
    strategy: str = "STABLE",
    note: str = ""
):
    """
    添加持仓
    
    Args:
        code: 股票代码
        name: 股票名称
        buy_price: 买入价格
        quantity: 买入数量
        strategy: 策略类型 (RPS_CORE=趋势核心, POTENTIAL=潜力股, STABLE=稳健标的)
        note: 备注
    """
    holdings = load_holdings()
    
    holdings[code] = {
        "name": name,
        "buy_price": buy_price,
        "buy_date": datetime.date.today().strftime("%Y-%m-%d"),
        "quantity": quantity,
        "strategy": strategy,
        "note": note
    }
    
    save_holdings(holdings)
    print(f"✅ 已添加持仓: {code} {name} @ {buy_price}")


def remove_position(code: str):
    """移除持仓"""
    holdings = load_holdings()
    
    if code in holdings:
        info = holdings.pop(code)
        save_holdings(holdings)
        print(f"✅ 已移除持仓: {code} {info['name']}")
    else:
        print(f"⚠️ 未找到持仓: {code}")


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
        if len(hist) < 5:
            return current_price, None, None
        
        # 计算实时 MA5
        closes = hist['收盘'].tail(4).tolist()
        ma5 = (sum(closes) + current_price) / 5
        
        is_below_ma5 = current_price < ma5
        
        return current_price, ma5, is_below_ma5
        
    except Exception as e:
        print(f"   获取 {code} 数据出错: {e}")
        return None, None, None


def daily_check():
    """
    每日持仓巡检
    检查是否跌破止损位
    """
    print("=" * 60)
    print("📋 持仓巡检")
    print(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    holdings = load_holdings()
    
    if not holdings:
        print("\n📭 当前无持仓")
        return
    
    print(f"\n当前持仓: {len(holdings)} 只\n")
    
    alerts = []
    
    for code, info in holdings.items():
        name = info['name']
        buy_price = info['buy_price']
        buy_date = info['buy_date']
        strategy = info.get('strategy', 'STABLE')
        
        # 获取实时数据
        current, ma5, below_ma5 = get_stock_ma5(code)
        
        if current is None:
            print(f"  ⚠️ {code} {name}: 数据获取失败")
            continue
        
        # 计算盈亏
        pnl = (current - buy_price) / buy_price * 100
        pnl_str = f"{pnl:+.2f}%"
        
        # 持仓天数
        days_held = (datetime.date.today() - datetime.datetime.strptime(buy_date, "%Y-%m-%d").date()).days
        
        # 状态判定
        status = "✅"
        action = ""
        
        if below_ma5:
            status = "🔴"
            action = "⚠️ 跌破MA5！"
            
            # 趋势核心股跌破MA5需要止损
            if strategy == "RPS_CORE":
                action = "🚨 止损信号！(跌破5日线)"
                alerts.append({
                    'code': code,
                    'name': name,
                    'current': current,
                    'ma5': ma5,
                    'pnl': pnl,
                    'action': '建议止损'
                })
        elif pnl < -5:
            status = "🟡"
            action = "注意亏损"
        elif pnl > 10:
            status = "🟢"
            action = "可考虑止盈"
        
        print(f"  {status} {code} {name}")
        print(f"     买入: {buy_price} ({buy_date}, 持有{days_held}天)")
        ma5_str = f"{ma5:.2f}" if ma5 else "N/A"
        print(f"     现价: {current:.2f} | MA5: {ma5_str} | 盈亏: {pnl_str}")
        if action:
            print(f"     👉 {action}")
        print()
    
    # 汇总警报
    if alerts:
        print("=" * 60)
        print("🚨 需要立即关注的持仓:")
        print("=" * 60)
        for alert in alerts:
            print(f"  ❗ {alert['code']} {alert['name']}: {alert['action']}")
            print(f"     现价: {alert['current']:.2f} < MA5: {alert['ma5']:.2f}")
        print("\n💡 建议: RPS_CORE 策略股票跌破5日线应止损出局！")


def list_holdings():
    """列出所有持仓"""
    holdings = load_holdings()
    
    if not holdings:
        print("📭 当前无持仓")
        return
    
    print("\n📋 当前持仓:")
    print("-" * 60)
    print(f"{'代码':<10} {'名称':<10} {'买入价':>8} {'日期':<12} {'策略':<12}")
    print("-" * 60)
    
    for code, info in holdings.items():
        print(f"{code:<10} {info['name']:<10} {info['buy_price']:>8.2f} {info['buy_date']:<12} {info.get('strategy', 'STABLE'):<12}")


def import_from_csv(csv_path: str = None, strategy: str = "STABLE"):
    """
    从选股结果 CSV 导入持仓
    
    Args:
        csv_path: CSV 文件路径，默认使用今日选股结果
        strategy: 默认策略类型
    """
    if csv_path is None:
        today = datetime.date.today().strftime('%Y%m%d')
        csv_path = os.path.join(RESULTS_DIR, f"选股结果_{today}.csv")
    
    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在: {csv_path}")
        return
    
    df = pd.read_csv(csv_path)
    
    print(f"\n📥 从 {os.path.basename(csv_path)} 导入持仓:")
    print("-" * 50)
    
    for _, row in df.iterrows():
        code = str(row['代码']).zfill(6)
        name = row['名称']
        price = row['现价']
        
        # 根据分类设定策略
        category = row.get('分类', '')
        if '趋势核心' in category:
            strat = 'RPS_CORE'
        elif '潜力股' in category:
            strat = 'POTENTIAL'
        else:
            strat = 'STABLE'
        
        print(f"  {code} {name} @ {price} [{strat}]")
        
        add_position(code, name, price, strategy=strat)
    
    print(f"\n✅ 已导入 {len(df)} 只股票")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='持仓管理')
    parser.add_argument('--check', action='store_true', help='每日巡检')
    parser.add_argument('--list', action='store_true', help='列出持仓')
    parser.add_argument('--add', type=str, help='添加持仓: 代码,名称,买入价 (例: 600000,浦发银行,10.5)')
    parser.add_argument('--remove', type=str, help='移除持仓: 代码')
    parser.add_argument('--import-csv', type=str, nargs='?', const='today', help='从 CSV 导入持仓')
    
    args = parser.parse_args()
    
    if args.check:
        daily_check()
    elif args.list:
        list_holdings()
    elif args.add:
        parts = args.add.split(',')
        if len(parts) >= 3:
            add_position(parts[0], parts[1], float(parts[2]))
        else:
            print("格式错误，应为: 代码,名称,买入价")
    elif args.remove:
        remove_position(args.remove)
    elif args.import_csv:
        if args.import_csv == 'today':
            import_from_csv()
        else:
            import_from_csv(args.import_csv)
    else:
        # 默认执行巡检
        daily_check()

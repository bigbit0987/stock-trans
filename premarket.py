#!/usr/bin/env python
"""
集合竞价预警脚本 (Pre-Market Alert)
在 9:20 - 9:25 运行，扫描持仓的集合竞价情况

功能：
1. 检测低开超过 -2% 的持仓（可能利空泄露，准备竞价出逃）
2. 核按钮预警：低开超过 -3% 立刻报警！（9:24 挂跌停价出逃）
3. 检测高开超过 +2% 的持仓（对于稳健标的考虑止盈）
4. 检测高开超过 +3% 的持仓（主力抢筹，可止盈一部分）
"""
import os
import sys
import datetime
import json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import akshare as ak
import pandas as pd

# 预警阈值配置
LOW_OPEN_THRESHOLD = -2.0      # 低开预警阈值 (%)
LOW_OPEN_CRITICAL = -3.0       # 核按钮预警阈值 (%)
HIGH_OPEN_STABLE = 2.0         # 稳健标的高开止盈阈值 (%)
HIGH_OPEN_THRESHOLD = 3.0      # 高开预警阈值 (%)

# 持仓文件路径
HOLDINGS_FILE = os.path.join(PROJECT_ROOT, "data", "holdings.json")


def load_holdings() -> dict:
    """加载持仓数据"""
    if os.path.exists(HOLDINGS_FILE):
        with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_premarket_data():
    """
    获取集合竞价数据
    
    注意：集合竞价期间(9:15-9:25)部分接口可能不稳定
    """
    try:
        # 使用实时行情接口，在9:20-9:25期间会返回集合竞价价格
        df = ak.stock_zh_a_spot_em()
        return df
    except Exception as e:
        print(f"⚠️ 获取集合竞价数据失败: {e}")
        return None


def check_premarket():
    """检查集合竞价情况"""
    print("=" * 60)
    print("📢 集合竞价预警")
    print(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 检查时间
    now = datetime.datetime.now()
    if now.hour != 9 or not (15 <= now.minute <= 30):
        print("\n⚠️ 当前不在集合竞价时间 (9:15-9:30)")
        print("   建议在 9:20-9:25 运行以获取集合竞价价格")
        print("   (继续运行将使用最新价格)")
    
    # 加载持仓
    holdings = load_holdings()
    if not holdings:
        print("\n📭 当前无持仓")
        return []
    
    print(f"\n当前持仓: {len(holdings)} 只\n")
    
    # 获取行情数据
    df = get_premarket_data()
    if df is None:
        return []
    
    alerts = []
    
    for code, info in holdings.items():
        name = info['name']
        
        # 获取该股票的数据
        stock = df[df['代码'] == code]
        if stock.empty:
            print(f"  ⚠️ {code} {name}: 数据获取失败")
            continue
        
        stock = stock.iloc[0]
        
        # 获取价格
        current_price = stock['最新价']  # 集合竞价期间这是竞价价格
        prev_close = stock['昨收']
        open_price = stock['今开'] if stock['今开'] > 0 else current_price
        
        # 计算跳空幅度
        gap_pct = (open_price - prev_close) / prev_close * 100
        
        # 获取策略类型
        strategy = info.get('strategy', 'STABLE')
        
        # 判断预警 (根据跳空幅度和策略类型)
        status = "✅"
        alert_info = None
        
        # 核按钮预警：低开超过 -3%，必须立刻处理！
        if gap_pct <= LOW_OPEN_CRITICAL:
            status = "🆘"  # 核按钮
            action = f"🚨 核按钮预警！低开 {gap_pct:.2f}%，9:24 挂跌停价出逃！"
            alert_info = {
                'code': code,
                'name': name,
                'open_price': open_price,
                'prev_close': prev_close,
                'gap_pct': gap_pct,
                'alert_type': 'CRITICAL',
                'strategy': strategy,
                'action': action
            }
            alerts.append(alert_info)
        # 普通低开预警
        elif gap_pct <= LOW_OPEN_THRESHOLD:
            status = "🔴"
            action = f"低开 {gap_pct:.2f}%，关注是否继续走弱"
            alert_info = {
                'code': code,
                'name': name,
                'open_price': open_price,
                'prev_close': prev_close,
                'gap_pct': gap_pct,
                'alert_type': 'LOW',
                'strategy': strategy,
                'action': action
            }
            alerts.append(alert_info)
        # 高开预警（根据策略区分）
        elif gap_pct >= HIGH_OPEN_THRESHOLD:
            status = "🟢"
            action = f"高开 {gap_pct:+.2f}%，可考虑止盈一部分"
            alert_info = {
                'code': code,
                'name': name,
                'open_price': open_price,
                'prev_close': prev_close,
                'gap_pct': gap_pct,
                'alert_type': 'HIGH',
                'strategy': strategy,
                'action': action
            }
            alerts.append(alert_info)
        # 稳健标的高开 +2% 即可考虑止盈
        elif strategy == 'STABLE' and gap_pct >= HIGH_OPEN_STABLE:
            status = "🟡"
            action = f"稳健标的高开 {gap_pct:+.2f}%，吃完这一口就跑！"
            alert_info = {
                'code': code,
                'name': name,
                'open_price': open_price,
                'prev_close': prev_close,
                'gap_pct': gap_pct,
                'alert_type': 'STABLE_HIGH',
                'strategy': strategy,
                'action': action
            }
            alerts.append(alert_info)
        
        # 打印信息
        print(f"  {status} {code} {name} [{strategy}]")
        print(f"     昨收: {prev_close:.2f} → 竞价: {open_price:.2f} (跳空: {gap_pct:+.2f}%)")
        if alert_info:
            print(f"     👉 {alert_info['action']}")
        print()
    
    # 汇总警报
    if alerts:
        print("=" * 60)
        print("🚨 需要立即关注:")
        print("=" * 60)
        for alert in alerts:
            if alert['alert_type'] == 'LOW':
                print(f"  🔴 {alert['code']} {alert['name']}: 低开 {alert['gap_pct']:.2f}%")
            else:
                print(f"  🟢 {alert['code']} {alert['name']}: 高开 {alert['gap_pct']:+.2f}%")
        print("\n💡 建议:")
        print("   - 低开超过 -2%: 可能有利空，考虑竞价/开盘卖出")
        print("   - 高开超过 +3%: 主力拉升，可考虑止盈一部分")
    else:
        print("✅ 所有持仓开盘正常，无需特别关注")
    
    return alerts


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='集合竞价预警')
    parser.add_argument('--push', action='store_true', help='推送预警到手机')
    
    args = parser.parse_args()
    
    alerts = check_premarket()
    
    # 推送预警
    if args.push and alerts:
        try:
            from src.notifier import notify_premarket_alert
            notify_premarket_alert(alerts)
            print("\n📱 预警已推送到手机")
        except Exception as e:
            print(f"\n⚠️ 推送失败: {e}")
            print("   请检查 config/settings.py 中的 NOTIFY 配置")

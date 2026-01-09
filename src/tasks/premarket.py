#!/usr/bin/env python
"""
集合竞价预警任务 (Pre-Market Alert)
在 9:20 - 9:25 运行，扫描持仓的集合竞价情况

v2.5.1: 改用 SQLite 数据库读取持仓
"""
import os
import sys
import datetime
import akshare as ak
import pandas as pd

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.utils import logger
from src.database import db
from src.data_loader import get_realtime_quotes

# 从配置文件读取阈值
try:
    from config import RISK_CONTROL
    LOW_OPEN_THRESHOLD = RISK_CONTROL.get('premarket_low_open', -2.0)
    LOW_OPEN_CRITICAL = RISK_CONTROL.get('premarket_critical', -3.0)
    HIGH_OPEN_STABLE = RISK_CONTROL.get('premarket_high_stable', 2.0)
    HIGH_OPEN_THRESHOLD = RISK_CONTROL.get('premarket_high_open', 3.0)
except ImportError:
    LOW_OPEN_THRESHOLD = -2.0
    LOW_OPEN_CRITICAL = -3.0
    HIGH_OPEN_STABLE = 2.0
    HIGH_OPEN_THRESHOLD = 3.0


def load_holdings() -> dict:
    """从 SQLite 加载持仓数据 (v2.5.1)"""
    return db.get_holdings()

def get_premarket_data():
    """获取并标准化实时行情 (v2.5.1)"""
    return get_realtime_quotes()

def check_premarket():
    logger.info("=" * 60)
    logger.info("📢 集合竞价预警启动")
    logger.info(f"   时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    now = datetime.datetime.now()
    if now.hour != 9 or not (15 <= now.minute <= 30):
        logger.warning("\n⚠️ 当前不在集合竞价时间 (9:15-9:30)")
        logger.warning("   建议在 9:20-9:25 运行以获取集合竞价行情")
    
    holdings = load_holdings()
    if not holdings:
        logger.info("\n📭 当前无持仓")
        return []
    
    logger.info(f"\n当前持仓: {len(holdings)} 只")
    
    df = get_premarket_data()
    if df is None:
        return []
    
    market_gap = 0
    market_status = "未知"
    try:
        index_df = ak.stock_zh_index_spot_em()
        sh_idx = index_df[index_df['代码'] == '000001']
        if not sh_idx.empty:
            market_gap = sh_idx.iloc[0]['涨跌幅']
            if market_gap <= -2:
                market_status = "🔴 系统性暴跌！情绪杀，建议警惕集体补跌"
            elif market_gap <= -1:
                market_status = "🟡 大盘低开"
            elif market_gap >= 1:
                market_status = "🟢 大盘高开，情绪良好"
            else:
                market_status = "⚪ 大盘平开"
    except Exception:
        pass
    
    logger.info(f"\n📊 大盘情况: 上证 {market_gap:+.2f}% {market_status}")
    logger.info("-" * 60)
    
    alerts = []
    for code, info in holdings.items():
        name = info['name']
        stock = df[df['code'] == code]
        if stock.empty:
            logger.warning(f"  ⚠️ {code} {name}: 数据获取失败")
            continue
        
        stock = stock.iloc[0]
        prev_close = stock['prev_close']
        open_price = stock['open'] if stock['open'] > 0 else stock['close']
        gap_pct = (open_price - prev_close) / prev_close * 100
        strategy = info.get('strategy', 'STABLE')
        
        status = "✅"
        alert_info = None
        
        if gap_pct <= LOW_OPEN_CRITICAL:
            status = "🆘"
            action = f"🚨 核按钮预警！低开 {gap_pct:.2f}%，9:24 挂跌停价出逃！"
            alert_info = {'code': code, 'name': name, 'gap_pct': gap_pct, 'alert_type': 'CRITICAL', 'action': action}
        elif gap_pct <= LOW_OPEN_THRESHOLD:
            status = "🔴"
            action = f"低开 {gap_pct:.2f}%，关注开盘能否承接"
            alert_info = {'code': code, 'name': name, 'gap_pct': gap_pct, 'alert_type': 'LOW', 'action': action}
        elif gap_pct >= HIGH_OPEN_THRESHOLD:
            status = "🟢"
            action = f"高开 {gap_pct:+.2f}%，主力拉升，可考虑止盈一部分"
            alert_info = {'code': code, 'name': name, 'gap_pct': gap_pct, 'alert_type': 'HIGH', 'action': action}
        elif strategy == 'STABLE' and gap_pct >= HIGH_OPEN_STABLE:
            status = "🟡"
            action = f"稳健标的高开 {gap_pct:+.2f}%，可兑现利润"
            alert_info = {'code': code, 'name': name, 'gap_pct': gap_pct, 'alert_type': 'STABLE_HIGH', 'action': action}
        
        logger.info(f"  {status} {code} {name} [{strategy}]")
        logger.info(f"     昨收: {prev_close:.2f} → 竞价: {open_price:.2f} (跳空: {gap_pct:+.2f}%)")
        if alert_info:
            logger.info(f"     👉 {alert_info['action']}")
            alerts.append(alert_info)
        logger.info("")
    
    if alerts:
        logger.info("=" * 60)
        logger.info("🚨 警报汇总:")
        logger.info("=" * 60)
        for alert in alerts:
            logger.info(f"  {alert.get('alert_type', 'INFO')} | {alert['code']} {alert['name']}: {alert['action']}")
    else:
        logger.info("✅ 所有持仓竞价正常")
    
    return alerts

if __name__ == "__main__":
    check_premarket()

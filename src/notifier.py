"""
消息推送模块
"""
import requests
import json
import hashlib
import hmac
import base64
import time
import urllib.parse
from datetime import datetime
from typing import List, Dict
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NOTIFY


def send_dingtalk(title: str, content: str) -> bool:
    """发送钉钉机器人消息"""
    webhook = NOTIFY.get('dingtalk_webhook', '')
    secret = NOTIFY.get('dingtalk_secret', '')
    
    if not webhook:
        return False
    
    url = webhook
    
    # 加签
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(
            secret.encode('utf-8'), 
            string_to_sign.encode('utf-8'), 
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"{webhook}&timestamp={timestamp}&sign={sign}"
    
    data = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": f"## {title}\n\n{content}"}
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json().get('errcode') == 0
    except:
        return False


def send_wechat(title: str, content: str) -> bool:
    """发送企业微信机器人消息"""
    webhook = NOTIFY.get('wechat_webhook', '')
    
    if not webhook:
        return False
    
    data = {
        "msgtype": "markdown",
        "markdown": {"content": f"## {title}\n\n{content}"}
    }
    
    try:
        response = requests.post(webhook, json=data, timeout=10)
        return response.json().get('errcode') == 0
    except:
        return False


def send_serverchan(title: str, content: str) -> bool:
    """发送 Server酱 消息"""
    key = NOTIFY.get('serverchan_key', '')
    
    if not key:
        return False
    
    url = f"https://sctapi.ftqq.com/{key}.send"
    
    try:
        response = requests.post(url, data={'title': title, 'desp': content}, timeout=10)
        return response.json().get('code') == 0
    except:
        return False


def format_stock_message(stocks: List[Dict]) -> str:
    """格式化选股结果为消息"""
    if not stocks:
        return "今日无符合条件的标的 😔"
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📅 扫描时间: {now}\n"]
    
    # 分类
    core = [s for s in stocks if '趋势核心' in s.get('分类', '')]
    potential = [s for s in stocks if '潜力股' in s.get('分类', '')]
    stable = [s for s in stocks if '稳健标的' in s.get('分类', '')]
    
    if core:
        lines.append("### ⭐ 趋势核心\n")
        for s in core:
            lines.append(f"- **{s['代码']} {s['名称']}** | {s['现价']} | RPS:{s['RPS']}")
    
    if potential:
        lines.append("\n### 🔥 潜力股\n")
        for s in potential:
            lines.append(f"- {s['代码']} {s['名称']} | {s['现价']} | RPS:{s['RPS']}")
    
    if stable:
        lines.append("\n### 📊 稳健标的\n")
        for s in stable[:5]:
            lines.append(f"- {s['代码']} {s['名称']} | {s['现价']}")
        if len(stable) > 5:
            lines.append(f"- ... 共 {len(stable)} 只")
    
    lines.append(f"\n> 总计: {len(stocks)} 只")
    return "\n".join(lines)


def notify_all(title: str, content: str) -> int:
    """
    推送到所有已配置的渠道
    
    Returns:
        成功推送的渠道数量
    """
    success = 0
    
    if send_dingtalk(title, content):
        print("✅ 钉钉推送成功")
        success += 1
    
    if send_wechat(title, content):
        print("✅ 企业微信推送成功")
        success += 1
    
    if send_serverchan(title, content):
        print("✅ Server酱推送成功")
        success += 1
    
    if success == 0:
        print("⚠️ 未配置推送渠道，请编辑 config/settings.py")
    
    return success


def notify_stock_signals(stocks: List[Dict]):
    """推送选股信号"""
    content = format_stock_message(stocks)
    notify_all("📊 尾盘选股信号", content)


def notify_position_alert(alerts: List[Dict]):
    """
    推送持仓预警
    
    Args:
        alerts: 预警列表，每个包含 code, name, current, ma5, action 等
    """
    if not alerts:
        return
    
    lines = [f"📅 预警时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    
    for alert in alerts:
        lines.append(f"🚨 **{alert['code']} {alert['name']}**")
        lines.append(f"   现价: {alert['current']:.2f} | MA5: {alert['ma5']:.3f}")
        lines.append(f"   👉 {alert['action']}\n")
    
    content = "\n".join(lines)
    notify_all("🚨 持仓止损预警", content)


def notify_simple(title: str, message: str):
    """
    发送简单消息
    
    Args:
        title: 标题
        message: 消息内容
    """
    notify_all(title, message)


def notify_premarket_alert(alerts: List[Dict]):
    """
    推送集合竞价预警
    
    Args:
        alerts: 预警列表，每个包含 code, name, open_price, prev_close, gap_pct, alert_type
    """
    if not alerts:
        return
    
    lines = [f"📅 集合竞价时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    
    for alert in alerts:
        if alert['alert_type'] == 'LOW':
            lines.append(f"🔴 **{alert['code']} {alert['name']}** 低开预警")
            lines.append(f"   昨收: {alert['prev_close']:.2f} → 竞价: {alert['open_price']:.2f}")
            lines.append(f"   跳空: {alert['gap_pct']:.2f}% ⚠️ 考虑竞价出逃\n")
        else:  # HIGH
            lines.append(f"🟢 **{alert['code']} {alert['name']}** 高开预警")
            lines.append(f"   昨收: {alert['prev_close']:.2f} → 竞价: {alert['open_price']:.2f}")
            lines.append(f"   跳空: {alert['gap_pct']:+.2f}% 💰 考虑高开获利\n")
    
    content = "\n".join(lines)
    notify_all("📢 集合竞价预警", content)


def notify_realtime_monitor(alerts: List[Dict]):
    """
    推送盘中实时监控预警
    
    Args:
        alerts: 预警列表，每个包含 code, name, type, current, buy_price, pnl_pct, message 等
    """
    if not alerts:
        return
    
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
            strategy = a.get('strategy', 'STABLE')
            if strategy == 'RPS_CORE':
                lines.append(f"  👉 趋势核心股，可继续持有观察")
            elif strategy == 'POTENTIAL':
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
            lines.append(f"  买入: {a['buy_price']} → 最高: {a.get('highest', 0):.2f} → 现价: {a['current']:.2f}")
            lines.append(f"  {a['message']}")
            lines.append(f"  👉 注意保护利润，考虑止盈")
            lines.append("")
    
    content = "\n".join(lines)
    notify_all("📡 盘中监控预警", content)


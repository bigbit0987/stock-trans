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

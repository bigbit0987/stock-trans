#!/usr/bin/env python
"""
数据迁移脚本 (JSON -> SQLite)
v2.5.0 升级程序
"""
import os
import json
import sys

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.database import db
from src.utils import logger, safe_read_json

def migrate_holdings():
    holdings_path = os.path.join(PROJECT_ROOT, "data", "holdings.json")
    if not os.path.exists(holdings_path):
        logger.info("⚠️ 未发现 holdings.json，跳过迁移")
        return

    logger.info("🚚 正在迁移持仓数据到 SQLite...")
    holdings = safe_read_json(holdings_path)
    
    count = 0
    for code, info in holdings.items():
        db.save_holding(code, info)
        count += 1
    
    logger.info(f"✅ 成功迁移 {count} 条持仓记录")
    
    # 备份并重命名旧文件
    # os.rename(holdings_path, holdings_path + ".bak")

if __name__ == "__main__":
    migrate_holdings()

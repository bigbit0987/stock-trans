#!/usr/bin/env python
"""
SQLite 存储引擎 (v2.5.0)
解决并发读写竞争风险，提供事务支持
"""
import sqlite3
import os
import datetime
from typing import Dict, List, Optional, Any
from src.utils import logger

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        # 增加超时配置，解决高并发写入锁争抢
        conn = sqlite3.connect(self.db_path, timeout=20)
        # 开启 WAL 模式，提升并发读写性能
        conn.execute('PRAGMA journal_mode=WAL')
        # v2.5.1: 优化写入性能，适用于 realtime_monitor 频繁更新
        conn.execute('PRAGMA synchronous=NORMAL')
        return conn

    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 持仓表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS holdings (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    buy_price REAL,
                    highest_price REAL,
                    buy_date TEXT,
                    quantity INTEGER,
                    strategy TEXT,
                    grade TEXT,
                    atr_stop REAL,
                    note TEXT
                )
            ''')
            # 交易历史表 (代替 trade_history.csv)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT,
                    name TEXT,
                    buy_date TEXT,
                    sell_date TEXT,
                    buy_price REAL,
                    sell_price REAL,
                    quantity INTEGER,
                    pnl_amount REAL,
                    pnl_pct REAL,
                    strategy TEXT,
                    grade TEXT,
                    note TEXT
                )
            ''')
            conn.commit()

    def get_holdings(self) -> Dict[str, dict]:
        """获取所有持仓 (保持原有 Dict 结构以保障兼容性)"""
        holdings = {}
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM holdings')
                rows = cursor.fetchall()
                for row in rows:
                    holdings[row['code']] = dict(row)
        except Exception as e:
            logger.error(f"数据库读取持仓失败: {e}")
        return holdings

    def save_holding(self, code: str, info: dict):
        """保存/更新单只持仓 (原子操作)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO holdings 
                    (code, name, buy_price, highest_price, buy_date, quantity, strategy, grade, atr_stop, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    code, info['name'], info['buy_price'], 
                    info.get('highest_price', info['buy_price']),
                    info['buy_date'], info['quantity'], 
                    info.get('strategy', 'STABLE'), 
                    info.get('grade', 'B'),
                    info.get('atr_stop'), info.get('note', '')
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库保存持仓失败 {code}: {e}")

    def remove_holding(self, code: str):
        """移除持仓"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM holdings WHERE code = ?', (code,))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库删除持仓失败 {code}: {e}")

    def add_trade_history(self, trade_data: dict):
        """记录交易历史"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO trade_history 
                    (code, name, buy_date, sell_date, buy_price, sell_price, quantity, pnl_amount, pnl_pct, strategy, grade, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade_data['code'], trade_data['name'], trade_data['buy_date'],
                    trade_data['sell_date'], trade_data['buy_price'], trade_data['sell_price'],
                    trade_data['quantity'], trade_data['pnl_amount'], trade_data['pnl_pct'],
                    trade_data.get('strategy'), trade_data.get('grade'), trade_data.get('note')
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库记录交易史失败: {e}")
    def get_trade_history(self) -> List[dict]:
        """获取所有交易历史"""
        history = []
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM trade_history ORDER BY sell_date DESC')
                rows = cursor.fetchall()
                for row in rows:
                    history.append(dict(row))
        except Exception as e:
            logger.error(f"数据库读取交易历史失败: {e}")
        return history

# 初始化全局数据库实例
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "alphahunter.db")
db = Database(DB_PATH)

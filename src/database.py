#!/usr/bin/env python
"""
SQLite 存储引擎 (v2.5.2)
解决并发读写竞争风险，提供事务支持
新增: Schema 版本控制，自动迁移
"""
import sqlite3
import os
import datetime
from typing import Dict, List, Optional, Any
from src.utils import logger

# v2.5.2: Schema 版本控制
# 每次修改表结构时，递增此版本号并在 _migrate_schema 中添加迁移逻辑
SCHEMA_VERSION = 2

class Database:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = None):
        if self._initialized:
            return
            
        # 默认路径处理
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, "data", "alphahunter.db")
            
        self.db_path = db_path
        self._init_db()
        self._initialized = True
        logger.debug(f"🗄️ 数据库引擎已就绪: {os.path.basename(self.db_path)}")

    def _get_connection(self):
        """获取数据库连接 (WAL模式)"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=20)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            return conn
        except sqlite3.OperationalError as e:
            logger.error(f"❌ 无法连接数据库: {e}")
            raise

    def check_write_permission(self) -> bool:
        """检查数据库文件及目录是否具备写权限"""
        try:
            # 1. 检查目录权限
            db_dir = os.path.dirname(self.db_path)
            if not os.access(db_dir, os.W_OK):
                logger.error(f"❌ 数据库目录不可写: {db_dir}")
                return False
                
            # 2. 检查文件权限 (如果文件已存在)
            if os.path.exists(self.db_path):
                if not os.access(self.db_path, os.W_OK):
                    logger.error(f"❌ 数据库文件不可写: {self.db_path}")
                    return False
            
            # 3. 尝试进行一次微小的写入测试
            with self._get_connection() as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS _write_test (id INTEGER PRIMARY KEY)")
                conn.execute("DROP TABLE _write_test")
            return True
        except Exception as e:
            logger.error(f"❌ 数据库权限检查失败: {e}")
            return False

    def _init_db(self):
        """初始化数据库表"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # v2.5.2: Schema 版本表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY
                    )
                ''')
                
                # 持仓表 (实盘/手动)
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
                # 虚拟持仓表 (v2.5.1 新增)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS virtual_holdings (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        buy_price REAL,
                        highest_price REAL,
                        buy_date TEXT,
                        rps REAL,
                        category TEXT,
                        suggestion TEXT,
                        closed INTEGER DEFAULT 0,
                        close_date TEXT,
                        close_price REAL,
                        close_reason TEXT,
                        pnl_pct REAL
                    )
                ''')
                # 虚拟交易历史表 (v2.5.1 新增)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS virtual_trade_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT,
                        name TEXT,
                        buy_price REAL,
                        buy_date TEXT,
                        sell_price REAL,
                        sell_date TEXT,
                        pnl_pct REAL,
                        category TEXT,
                        rps REAL,
                        reason TEXT,
                        type TEXT,
                        days_held INTEGER
                    )
                ''')
                # 每日推荐记录表 (v2.5.1 新增 - 代替 recommendations.json)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS recommendations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,
                        code TEXT,
                        name TEXT,
                        buy_price REAL,
                        rps REAL,
                        category TEXT,
                        suggestion TEXT,
                        day1_pnl REAL,
                        day3_pnl REAL,
                        day5_pnl REAL,
                        UNIQUE(date, code)
                    )
                ''')
                # 实时提醒历史表 (v2.5.1 新增 - 用于冷却机制)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alert_history (
                        key TEXT PRIMARY KEY,
                        last_alert_time TEXT
                    )
                ''')
                conn.commit()
                
                # v2.5.2: 检查并执行 Schema 迁移
                self._check_and_migrate_schema(conn)
                
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")

    def _check_and_migrate_schema(self, conn):
        """检查 Schema 版本并执行必要的迁移 (v2.5.2 新增)"""
        try:
            cursor = conn.cursor()
            
            # 获取当前数据库版本
            cursor.execute('SELECT version FROM schema_version ORDER BY version DESC LIMIT 1')
            row = cursor.fetchone()
            current_version = row[0] if row else 0
            
            if current_version < SCHEMA_VERSION:
                logger.info(f"🔄 检测到 Schema 版本需要更新: {current_version} → {SCHEMA_VERSION}")
                self._migrate_schema(conn, current_version, SCHEMA_VERSION)
                
                # 更新版本号
                cursor.execute('INSERT OR REPLACE INTO schema_version (version) VALUES (?)', (SCHEMA_VERSION,))
                conn.commit()
                logger.info(f"✅ Schema 迁移完成，当前版本: {SCHEMA_VERSION}")
            else:
                logger.debug(f"Schema 版本最新: {SCHEMA_VERSION}")
                
        except Exception as e:
            logger.warning(f"Schema 版本检查失败 (可忽略): {e}")
    
    def _migrate_schema(self, conn, from_version: int, to_version: int):
        """执行增量 Schema 迁移 (v2.5.2 新增)
        
        每次修改表结构时，在此添加迁移逻辑。
        迁移写法示例:
        - if from_version < 2: cursor.execute("ALTER TABLE xxx ADD COLUMN yyy TEXT")
        """
        cursor = conn.cursor()
        
        # 版本 1 -> 2: 示例迁移 (添加 virtual_holdings.grade 列)
        if from_version < 2:
            try:
                # 检查 grade 列是否存在
                cursor.execute("PRAGMA table_info(virtual_holdings)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'grade' not in columns:
                    cursor.execute("ALTER TABLE virtual_holdings ADD COLUMN grade TEXT DEFAULT 'B'")
                    logger.info("   迁移: 为 virtual_holdings 添加 grade 列")
            except Exception as e:
                logger.debug(f"迁移 v2 失败 (可忽略): {e}")
        
        # 未来版本的迁移在此添加:
        # if from_version < 3:
        #     cursor.execute("ALTER TABLE ...")
        
        conn.commit()

    def get_alert_history(self) -> Dict[str, str]:
        """获取所有提醒历史记录"""
        history = {}
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM alert_history')
                rows = cursor.fetchall()
                for row in rows:
                    history[row['key']] = row['last_alert_time']
        except Exception as e:
            logger.error(f"数据库读取提醒历史失败: {e}")
        return history

    def save_alert_history(self, key: str, last_time: str):
        """保存单条提醒历史"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT OR REPLACE INTO alert_history (key, last_alert_time) VALUES (?, ?)', (key, last_time))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库保存提醒历史失败: {e}")

    def clear_alert_history(self, cutoff_time: str):
        """清空指定时间之前的提醒记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM alert_history WHERE last_alert_time < ?', (cutoff_time,))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库清理提醒历史失败: {e}")

    def get_recommendations(self, date_str: str = None) -> List[dict]:
        """获取推荐记录"""
        history = []
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if date_str:
                    cursor.execute('SELECT * FROM recommendations WHERE date = ?', (date_str,))
                else:
                    cursor.execute('SELECT * FROM recommendations ORDER BY date DESC')
                rows = cursor.fetchall()
                for row in rows:
                    history.append(dict(row))
        except Exception as e:
            logger.error(f"数据库读取推荐记录失败: {e}")
        return history

    def save_recommendation(self, rec: dict):
        """保存推荐记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO recommendations 
                    (date, code, name, buy_price, rps, category, suggestion, day1_pnl, day3_pnl, day5_pnl)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    rec['date'], rec['code'], rec['name'], rec['buy_price'],
                    rec.get('rps', 0), rec.get('category', ''), rec.get('suggestion', ''),
                    rec.get('day1_pnl'), rec.get('day3_pnl'), rec.get('day5_pnl')
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库保存推荐记录失败: {e}")

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

    # --- 虚拟持仓相关 (v2.5.1) ---
    def get_virtual_holdings(self, only_active: bool = True) -> Dict[str, dict]:
        """获取虚拟持仓"""
        holdings = {}
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                query = 'SELECT * FROM virtual_holdings'
                if only_active:
                    query += ' WHERE closed = 0'
                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    holdings[row['code']] = dict(row)
        except Exception as e:
            logger.error(f"数据库读取虚拟持仓失败: {e}")
        return holdings

    def save_virtual_holding(self, code: str, info: dict):
        """保存/更新虚拟持仓"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO virtual_holdings 
                    (code, name, buy_price, highest_price, buy_date, rps, category, suggestion, closed, close_date, close_price, close_reason, pnl_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    code, info['name'], info['buy_price'], 
                    info.get('highest_price', info['buy_price']),
                    info['buy_date'], info.get('rps', 0),
                    info.get('category', ''), info.get('suggestion', ''),
                    1 if info.get('closed', False) else 0,
                    info.get('close_date'), info.get('close_price'),
                    info.get('close_reason'), info.get('pnl_pct')
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库保存虚拟持仓失败 {code}: {e}")

    def add_virtual_trade_history(self, trade_data: dict):
        """记录虚拟交易历史"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO virtual_trade_history 
                    (code, name, buy_price, buy_date, sell_price, sell_date, pnl_pct, category, rps, reason, type, days_held)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade_data['code'], trade_data['name'], 
                    trade_data['buy_price'], trade_data['buy_date'],
                    trade_data['sell_price'], trade_data['sell_date'],
                    trade_data['pnl_pct'], trade_data.get('category'),
                    trade_data.get('rps'), trade_data.get('reason'),
                    trade_data.get('type'), trade_data.get('days_held')
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"数据库记录虚拟交易史失败: {e}")

    def get_virtual_trade_history(self) -> List[dict]:
        """获取所有虚拟交易历史"""
        history = []
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM virtual_trade_history ORDER BY sell_date DESC')
                rows = cursor.fetchall()
                for row in rows:
                    history.append(dict(row))
        except Exception as e:
            logger.error(f"数据库读取虚拟交易历史失败: {e}")
        return history

    def clear_virtual_holdings(self):
        """清空虚拟持仓表"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM virtual_holdings')
                conn.commit()
        except Exception as e:
            logger.error(f"数据库清空虚拟持仓失败: {e}")

# 初始化全局数据库实例
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "alphahunter.db")
db = Database(DB_PATH)

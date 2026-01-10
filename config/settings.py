"""
AlphaHunter - 尾盘低吸选股系统
配置文件
"""

# ============================================
# 基础路径配置
# ============================================
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据目录
DATA_DIR = os.path.join(BASE_DIR, "data")
RPS_DATA_DIR = os.path.join(DATA_DIR, "rps")
HISTORY_DATA_DIR = os.path.join(DATA_DIR, "history")

# 输出目录
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
RESULTS_DIR = os.path.join(OUTPUT_DIR, "results")
BACKTEST_DIR = os.path.join(OUTPUT_DIR, "backtest")

# 确保目录存在
for dir_path in [RPS_DATA_DIR, HISTORY_DATA_DIR, RESULTS_DIR, BACKTEST_DIR]:
    os.makedirs(dir_path, exist_ok=True)


# ============================================
# 策略参数配置
# ============================================
STRATEGY = {
    # 涨跌幅筛选 (小阳线)
    'pct_change_min': 0.3,      # 最小涨幅 %
    'pct_change_max': 4.0,      # 最大涨幅 %
    
    # 换手率筛选 (流动性)  
    'turnover_min': 5.0,        # 最小换手率 %
    'turnover_max': 20.0,       # 最大换手率 %
    
    # 量比筛选 (人气)
    'volume_ratio_min': 0.8,    # 最小量比
    
    # 振幅筛选 (波动小)
    'amplitude_max': 0.05,      # 最大振幅 5%
    
    # MA5 乖离率 (紧紧相连)
    'ma5_bias_max': 0.02,       # 与MA5乖离率不超过 2%
    
    # RPS 筛选
    'rps_min': 40,              # 最低 RPS 评分
    'rps_window': 120,          # RPS 计算周期（天）- 长周期趋势
    'rps_short_window': 20,     # v2.4: 短期RPS周期（捕捉短期爆发）
    
    # v2.4.1 新增: 前一天小阳线条件 (原硬编码在 strategy.py)
    'prev_day_pct_min': 0,      # 前一天最小涨幅 %
    'prev_day_pct_max': 5,      # 前一天最大涨幅 %
    
    # v2.4.1 新增: RPS"弱转强"信号阈值 (借鉴 Qbot 策略)
    'rps_weak_to_strong': {
        'rps120_threshold': 70,     # RPS120 低于此值视为"弱"
        'rps20_breakthrough': 90,   # RPS20 突破此值视为"转强"
        'enabled': True,            # 是否启用弱转强检测
    },
}


# ============================================
# 量价策略配置 (v2.4 新增)
# 策略报告关键改进点：区分"缩量蓄势"与"放量滞涨"
# ============================================
VOLUME_PRICE_STRATEGY = {
    # 是否启用量价协同判断
    'enabled': True,
    
    # 放量滞涨判定阈值
    'stagnant_volume': {
        'max_pct_change': 1.0,       # 涨幅小于1%
        'min_volume_ratio': 2.5,     # 量比大于2.5
        'action': 'warn',            # 'filter'=过滤掉, 'warn'=标注警告, 'downgrade'=降级
    },
    
    # 缩量蓄势判定阈值
    'shrinking_volume': {
        'max_pct_change': 3.0,       # 涨幅在0-3%
        'max_volume_ratio': 1.0,     # 量比小于1.0
        'bonus_score': 15,           # 额外加分
    },
    
    # 健康放量上涨阈值
    'healthy_volume': {
        'min_pct_change': 2.0,       # 涨幅大于2%
        'volume_ratio_range': [1.2, 2.5],  # 量比在1.2-2.5之间
    },
    
    # 极度缩量警告
    'extremely_low_volume': {
        'max_volume_ratio': 0.5,     # 量比小于0.5
        'action': 'warn',            # 流动性风险警告
    },
}


# ============================================
# 多因子策略配置 (v2.3 新增)
# ============================================
MULTI_FACTOR = {
    # 是否启用多因子评分
    'enabled': True,
    
    # 因子权重 (总和应为1.0)
    'weights': {
        'rps': 0.30,            # 动量因子 (RPS)
        'money_flow': 0.25,     # 资金流向因子
        'sector': 0.20,         # 板块热度因子
        'valuation': 0.15,      # 估值因子
        'technical': 0.10,      # 技术因子 (预留)
    },
    
    # 最低综合评分 (低于此分不推荐)
    'min_total_score': 60,
    
    # 各因子最低分限制
    'min_scores': {
        'rps': 40,              # RPS至少40
        'money_flow': 30,       # 资金流向至少30
    },
}

# 验证因子权重配置
def _validate_factor_weights():
    """验证因子权重总和是否为1.0，如果不是则发出警告"""
    weights = MULTI_FACTOR.get('weights', {})
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:  # 允许微小的浮点误差
        import warnings
        warnings.warn(
            f"⚠️ 多因子权重配置错误: 总和为 {total:.2f}，应为 1.0。"
            f"请检查 MULTI_FACTOR['weights'] 配置。",
            UserWarning
        )

_validate_factor_weights()


# ============================================
# 大盘风控配置 (v2.5.2 增强)
# ============================================
MARKET_RISK_CONTROL = {
    # 是否启用大盘风控
    'enabled': True,
    
    # 大盘在20日均线之下时的行为
    'below_ma20_action': 'warn',  # 'stop'=停止选股(休眠模式), 'warn'=警告但继续, 'ignore'=忽略
    
    # 大盘单日跌幅阈值
    'index_drop_threshold': -2.0,  # 大盘跌超2%暂停选股
    
    # 赚钱效应阈值 (上涨股票占比)
    'sentiment_threshold': 0.3,    # 低于30%时减少操作
    
    # 休眠模式 (v2.3.1 新增)
    'sleep_mode': {
        'enabled': True,               # 是否启用休眠模式
        'trigger': 'below_ma20',       # 触发条件: 'below_ma20' 或 'consecutive_down_3'
        'notify_on_sleep': True,       # 进入休眠时发送通知
    },
    
    # v2.5.2 新增: 市场宽度自适应配置
    # 根据市场宽度动态调整筛选标准
    'market_breadth_adaptive': {
        'enabled': True,
        # 冰点期 (breadth < 8%): 只做最强核心标的
        'cold_market': {
            'threshold': 8,            # 市场宽度 < 8%
            'rps_min_override': 70,    # RPS 最低要求提高到 70
            'position_multiplier': 0.5, # 仓位减半
        },
        # 过热期 (breadth > 30%): 警惕情绪过热
        'hot_market': {
            'threshold': 30,           # 市场宽度 > 30%
            'turnover_spike_check': True,  # 启用换手率突变检测
            'turnover_spike_ratio': 3.0,   # 换手率突变倍数阈值 (相比5日均值)
        },
    },
}


# ============================================
# 高级止损策略配置 (v2.3.1 新增)
# ============================================
STOP_LOSS_STRATEGY = {
    # 止损模式: 'fixed'=固定MA5, 'atr'=动态ATR, 'hybrid'=混合
    'mode': 'hybrid',
    
    # ATR参数
    'atr_period': 14,               # ATR计算周期
    'atr_multiplier': 2.0,          # ATR倍数 (2倍ATR止损)
    
    # 固定止损
    'fixed_stop_pct': -3.0,         # 固定止损百分比
    
    # 移动止盈 (trailing stop)
    'trailing_stop': {
        'enabled': True,
        'activation_pct': 5.0,      # 盈利超过5%后激活移动止损
        'callback_pct': 3.0,        # 从最高点回撤3%止盈
    },
}


# ============================================
# 凯利公式仓位配置 (v2.3.1 新增)
# ============================================
KELLY_POSITION = {
    # 是否启用凯利公式
    'enabled': True,
    
    # 基础单笔金额 (会根据胜率动态调整)
    'base_amount': 50000,
    
    # 安全系数 (使用N倍凯利值，通常0.5即半凯利)
    'safety_factor': 0.5,
    
    # 最小/最大仓位限制
    'min_position_pct': 0.2,        # 最小为基础金额的20%
    'max_position_pct': 2.0,        # 最大为基础金额的200%
    
    # 胜率阈值
    'thresholds': {
        'excellent': 0.70,          # 胜率≥70%时加大仓位
        'good': 0.55,               # 胜率≥55%时正常仓位
        'average': 0.40,            # 胜率≥40%时减少仓位
        # 低于40%时最小仓位
    },
}


# ============================================
# 板块滤网配置 (v2.3.1 新增)
# ============================================
SECTOR_FILTER = {
    # 是否启用板块滤网
    'enabled': True,
    
    # 只买入处于全市场前N%的板块内的股票
    'top_pct': 0.33,               # 前1/3 (约前30个板块)
    
    # 板块共振加分
    'resonance_bonus': {
        'top3': 15,                # TOP3板块额外加15分
        'top5': 10,                # TOP5板块额外加10分
        'top10': 5,                # TOP10板块额外加5分
    },
}


# ============================================
# 回测参数配置
# ============================================
BACKTEST = {
    'start_date': '20240101',   # 回测开始日期
    'end_date': '20241220',     # 回测结束日期
    'commission': 0.0003,       # 佣金 0.03%
    'stamp_duty': 0.001,        # 印花税 0.1%
    'sample_size': 500,         # 抽样股票数量
}


# ============================================
# 消息推送配置 (请填入你的配置)
# ============================================
NOTIFY = {
    # 钉钉机器人
    'dingtalk_webhook': os.getenv('DINGTALK_WEBHOOK', ''),
    'dingtalk_secret': os.getenv('DINGTALK_SECRET', ''),
    
    # 企业微信机器人
    'wechat_webhook': '',       # 企业微信 Webhook URL
    
    # Server酱 (微信推送)
    'serverchan_key': '',       # Server酱 SendKey
}


# ============================================
# 定时任务配置
# ============================================
SCHEDULER = {
    'update_rps_time': '17:00',     # RPS 更新时间
    'scan_time_1': '14:35',         # 第一次扫描
    'scan_time_2': '14:50',         # 第二次扫描（临近收盘）
}


# ============================================
# 并发配置
# ============================================
CONCURRENT = {
    'max_workers': 30,          # 最大并发线程数 (从10提升到30)
    'batch_size': 100,          # 批处理大小
}

# ============================================
# 网络请求配置
# ============================================
NETWORK = {
    'timeout': 10,              # 请求超时(秒)
    'max_retries': 3,           # 最大重试次数
    'retry_delay': 0.5,         # 重试间隔(秒)
}

# ============================================
# 缓存配置
# ============================================
CACHE = {
    'enabled': True,            # 是否启用缓存
    'ttl_hours': 24,            # 缓存有效期(小时)
    'history_days': 150,        # 历史数据缓存天数(多存一些备用)
}


# ============================================
# 黑名单配置 (从外部文件读取)
# ============================================
def load_blacklist():
    """从 blacklist.txt 读取黑名单"""
    blacklist_file = os.path.join(os.path.dirname(__file__), 'blacklist.txt')
    blacklist = []
    
    if os.path.exists(blacklist_file):
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if line and not line.startswith('#'):
                    # 取代码部分（忽略后面的注释）
                    code = line.split()[0] if line.split() else line
                    if code:
                        blacklist.append(code)
    
    return blacklist

BLACKLIST = load_blacklist()


# ============================================
# 风控配置
# ============================================
RISK_CONTROL = {
    'market_drop_threshold': -1.5,  # 大盘跌幅阈值（超过此值给出警告）
    'sentiment_threshold': 0.2,     # 赚钱效应阈值（上涨家数占比低于此值警告）

       
    # 集合竞价预警阈值
    'premarket_low_open': -2.0,     # 低开预警阈值 (%)
    'premarket_critical': -3.0,     # 核按钮预警阈值 (%)
    'premarket_high_stable': 2.0,   # 稳健标的高开止盈阈值 (%)
    'premarket_high_open': 3.0,     # 高开预警阈值 (%)
}


# ============================================
# 盘中实时监控配置
# ============================================
REALTIME_MONITOR = {
    # 监控间隔 (秒)
    'check_interval': 60,           # 每60秒检查一次
    
    # 冲高止盈提醒阈值 (%)
    'take_profit_levels': [3, 5, 10],   # 涨幅达到这些点位时提醒
    
    # 止损提醒阈值 (%)
    'stop_loss_level': -3,          # 跌破买入价3%提醒
    
    # 回调提醒 (从最高点回撤)
    'drawdown_alert': -3,           # 从最高点回撤3%提醒
    
    # 回撤监控触发条件 (v2.4.1 新增: 之前硬编码在 realtime_monitor.py 中)
    'drawdown_monitor_min_profit': 3,   # 浮盈超过此值后才监控回撤 (%)
    
    # 交易时间段
    'trading_start': '09:30',       # 开盘时间
    'trading_end': '15:00',         # 收盘时间
    'lunch_start': '11:30',         # 午休开始
    'lunch_end': '13:00',           # 午休结束
    
    # 提醒冷却时间 (秒) - 同一股票同一类型提醒的最小间隔
    'alert_cooldown': 3600,         # 1小时内同类型提醒只发一次
}


# ============================================
# 持仓巡检配置 (v2.4.1 新增)
# ============================================
PORTFOLIO_CHECK = {
    # 回撤止盈警报条件
    'max_profit_threshold': 10,     # 历史最高浮盈达到此值后 (%)
    'drawdown_threshold': -3,       # 回撤超过此值触发警报 (%)
    
    # 止盈提醒阈值
    'take_profit_alert': 10,        # 当前盈利超过此值提醒 (%)
    
    # 亏损关注阈值
    'loss_attention_threshold': -5, # 亏损超过此值时标记需关注 (%)
}


# ============================================
# 推荐效果追踪配置
# ============================================
PERFORMANCE_TRACKING = {
    # 追踪周期 (天)
    'track_days': [1, 3, 5],        # 追踪推荐后1日、3日、5日表现
    
    # 报告生成
    'weekly_report': True,          # 是否生成周报
    'monthly_report': True,         # 是否生成月报
}


# ============================================
# 资金与仓位管理
# ============================================
CAPITAL = {
    'target_amount_per_stock': 50000, # 每只股票计划买入金额 (元)
}

# 📈 AlphaHunter - 尾盘低吸选股系统

> 基于十年实战经验的量化选股工具，结合"尾盘低吸"策略 + RPS 强度评分

---

## 📁 项目结构

```
stock_trans/
│
├── 📄 main.py              # 🚀 【系统总指挥】统一命令行入口
├── 📄 scheduler.py         # ⏰ 【自动化入口】定时任务调度
├── 📄 requirements.txt     # 📦 依赖包清单
│
├── 📁 config/              # ⚙️ 配置文件目录
│   ├── settings.py         # 核心参数配置
│   ├── settings.py.example # 配置模板
│   └── blacklist.txt       # 股票黑名单
│
├── 📁 src/                 # 🔧 核心源码
│   ├── utils.py            # 全局日志与工具
│   ├── data_loader.py      # 数据底座
│   ├── strategy.py         # 策略算法
│   ├── notifier.py         # 消息推送
│   └── tasks/              # 🛠️ 业务逻辑下沉 (逻辑中心)
│       ├── scanner.py      # 选股逻辑
│       ├── portfolio.py    # 持仓管理
│       ├── updater.py      # 数据更新
│       ├── premarket.py    # 竞价预警
│       ├── backtester.py   # 回测引擎
│       └── dashboard.py    # 战绩分析
│
├── 📁 data/                # 📦 私人数据库 (gitignore)
│   ├── holdings.json       # 持仓详情
│   ├── trade_history.csv   # 交易全记录
│   └── back_up/            # 数据备份
│
├── 📁 output/              # 📤 临时输出 (gitignore)
│   ├── results/            # 每日选股结果
│   └── backtest/           # 策略回测报告
│
├── 📁 logs/                # 📋 系统日志 (按天记录)
│
└── 📁 docs/                # 📚 知识库
    └── 策略思路.md
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install akshare pandas schedule requests
```

### 2. 更新 RPS 数据 (首次运行)

```bash
python update_rps.py
```

### 3. 运行选股扫描

```bash
python scan.py
```

---

## 📊 核心命令 (推荐使用 main.py)

```bash
# 统一入口
python main.py scan              # 🔍 尾盘选股
python main.py check --push      # 📋 持仓巡检 + 推送
python main.py premarket --push  # 📢 集合竞价预警 + 推送
python main.py update            # 📊 更新RPS数据
python main.py dashboard         # 📈 查看交易战绩
python main.py backtest          # 📉 策略回测

# 盘中实时监控 (新增 v2.2)
python main.py monitor           # 📡 持续监控(直到收盘)
python main.py monitor --once    # 只检查一次
python main.py monitor --duration 60  # 监控60分钟
python main.py monitor --clear   # 清理提醒历史

# 推荐效果统计 (新增 v2.2)
python main.py performance       # 📊 查看推荐效果报告
python main.py performance --update   # 更新追踪数据
python main.py performance --push     # 推送周报
python main.py performance --cleanup 30  # 清理30天前的记录

# 持仓管理
python main.py add 600000 浦发银行 10.5 1000
python main.py close 600000 11.0
python main.py close 600000 11.0 500         # 减仓500股
python main.py close 600000 11.0 --force     # 强制卖出(跳过T+1)
python main.py import                        # 导入选股结果
python main.py list                          # 列出持仓
python main.py history                       # 交易历史

# 缓存管理
python main.py cache status      # 📦 查看缓存状态
python main.py cache clean       # 🧹 清理过期缓存
```

| 命令                       | 说明             | 建议时间            |
| -------------------------- | ---------------- | ------------------- |
| `main.py update`           | 更新 RPS 数据    | 每天 17:00 (收盘后) |
| `main.py premarket --push` | 集合竞价预警     | 9:20 - 9:25         |
| `main.py monitor`          | **盘中实时监控** | 9:30 - 15:00        |
| `main.py check --push`     | 持仓巡检         | 早盘/盘中           |
| `main.py scan`             | 尾盘选股         | 14:35 - 14:50       |
| `main.py import`           | 导入持仓         | 尾盘后              |
| `main.py performance`      | **推荐效果统计** | 收盘后              |
| `main.py cache status`     | 查看缓存         | 随时                |

---

## 📋 持仓管理

### 添加持仓

```bash
# 从选股结果导入（推荐）
python position.py --import-csv

# 手动添加
python position.py --add 600000,浦发银行,10.5
```

### 每日巡检（检查止损位）

```bash
python position.py --check
```

会检查每只持仓是否跌破 MA5，对于 `RPS_CORE` 策略的股票给出止损警告。

### 平仓（支持减仓）

```bash
# 使用当前价全部平仓
python position.py --close 600000

# 指定卖出价全部平仓
python position.py --close 600000,11.5

# 减仓500股（潜力股次日冲高卖一半）
python position.py --close 600000,11.5,500
```

平仓后会自动归档到 `data/trade_history.csv`。

### 查看交易历史

```bash
python position.py --history
```

显示所有已平仓的交易记录和胜率统计。

### 其他命令

```bash
python position.py --list    # 列出所有持仓
python position.py --remove 600000  # 移除持仓（不归档）
```

---

## ⚙️ 配置说明

所有参数集中在 `config/settings.py`:

### 策略参数

```python
STRATEGY = {
    'pct_change_min': 0.3,      # 最小涨幅 %
    'pct_change_max': 4.0,      # 最大涨幅 %
    'turnover_min': 5.0,        # 最小换手率 %
    'turnover_max': 20.0,       # 最大换手率 %
    'ma5_bias_max': 0.02,       # MA5 乖离率上限
    'rps_min': 40,              # 最低 RPS 评分
}
```

### 推送配置

```python
NOTIFY = {
    'dingtalk_webhook': '',     # 钉钉 Webhook
    'wechat_webhook': '',       # 企业微信 Webhook
    'serverchan_key': '',       # Server酱 Key
}
```

---

## 🏷️ 选股分类

| 分类        | RPS 范围 | 操作建议                    |
| ----------- | -------- | --------------------------- |
| ⭐ 趋势核心 | ≥ 90     | 可多拿几天，跌破 5 日线止损 |
| 🔥 潜力股   | 75-89    | 次日冲高卖一半，留一半观察  |
| 📊 稳健标的 | 40-74    | 次日冲高即走                |

---

## 📅 日常流程

```
┌─────────────────────────────────────────────────────┐
│  前一天晚上                                          │
│    └─ python update_rps.py   # 更新强度数据          │
├─────────────────────────────────────────────────────┤
│  14:35                                               │
│    └─ python scan.py         # 运行选股              │
├─────────────────────────────────────────────────────┤
│  14:50 - 15:00                                       │
│    └─ 查看结果，尾盘买入                             │
│       ⭐ 趋势核心 → 多拿几天                         │
│       📊 稳健标的 → 次日即走                         │
├─────────────────────────────────────────────────────┤
│  次日                                                │
│    └─ 根据建议执行卖出                               │
└─────────────────────────────────────────────────────┘
```

---

## 🧠 策略核心

### 尾盘低吸逻辑

- **时机**: 下午 2:30 后，全天走势已定
- **形态**: 连涨两天小阳 + 紧贴 5 日线
- **风控**: 次日冲高即走，风险可控

### RPS 增强

- 只买市场最强的品种 (RPS > 40)
- 趋势核心股可适当延长持仓
- 自动排除弱势补涨股

---

## ⚠️ 风控原则

1. **不买弱势股**: RPS < 40 坚决不碰
2. **不追高**: 只做"蓄势"形态，不追涨停
3. **严格止损**: 跌破 5 日线必走
4. **熊市减仓**: 大盘持续下跌时降低仓位

---

## 📝 更新日志

- **v2.2** (2026-01-07): 📡 智能监控版
  - 新增 `monitor` 盘中实时监控命令
    - 支持止盈提醒（涨幅达 3%/5%/10% 时钉钉通知）
    - 支持止损提醒（跌破买入价 3% 时提醒）
    - 支持回撤提醒（从最高点回撤超 3% 时提醒）
    - 智能冷却机制，避免频繁骚扰
  - 新增 `performance` 推荐效果统计命令
    - 自动记录每日推荐的股票
    - 追踪推荐后 1 日、3 日、5 日 的涨跌幅
    - 统计胜率、平均收益率
    - 支持生成周报/月报
  - 调度器新增盘中监控任务（每天 6 次检查）
- **v2.1** (2024-12-23): 🚀 性能优化版
  - 新增智能缓存系统（Parquet 格式存储）
  - 并发数从 10 提升到 30
  - 增量更新机制，避免重复 API 请求
  - 缓存命中后速度提升 **400 倍**
  - 新增 `cache` 命令管理缓存
- **v2.0** (2024-12-23): 重构项目结构，模块化设计
- **v1.0** (2024-12-23): 初始版本

---

## ⚠️ 免责声明

本工具仅供学习研究，不构成投资建议。
股市有风险，投资需谨慎。

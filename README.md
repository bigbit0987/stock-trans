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
│   ├── factors.py          # 因子计算 (v2.3)
│   ├── indicators.py       # 技术指标 (ATR等)
│   └── tasks/              # 🛠️ 业务逻辑下沉 (逻辑中心)
│       ├── scanner.py      # 选股逻辑
│       ├── portfolio.py    # 持仓管理
│       ├── updater.py      # 数据更新
│       ├── premarket.py    # 竞价预警
│       ├── backtester.py   # 回测引擎
│       ├── dashboard.py    # 战绩分析
│       ├── virtual_tracker.py   # 🧪 虚拟持仓追踪
│       ├── performance_tracker.py # 📊 推荐效果统计
│       └── realtime_monitor.py    # 📡 盘中实时监控
│
├── 📁 data/                # 📦 私人数据库 (gitignore)
│   ├── alphahunter.db      # 🗄️ SQLite 数据库 (持仓 + 交易历史)
│   ├── holdings.json       # [废弃] 旧版持仓文件
│   ├── virtual_positions.json # 虚拟持仓记录
│   ├── virtual_trades.json    # 虚拟交易历史
│   └── ...                 # RPS 数据与历史缓存
│
├── 📁 output/              # 📤 临时输出 (gitignore)
│   ├── results/            # 每日选股结果 (CSV)
│   └── backtest/           # 策略回测报告
│
├── 📁 logs/                # 📋 系统日志 (按天记录)
└── 📁 .agent/              # 🤖 工作流定义
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置密钥

复制 `.env.example` 为 `.env` 并填入您的钉钉 Webhook 等配置：

```bash
cp .env.example .env
# 编辑 .env 填入 DINGTALK_WEBHOOK 和 DINGTALK_SECRET
```

### 3. 一键初始化与更新

```bash
python main.py update            # 更新 RPS 强度数据
```

### 4. 开启每日自动化

```bash
# 直接运行脚本执行全套任务（RPS更新 -> 尾盘扫描 -> 持仓巡检 -> 虚拟追踪）
./run_daily.sh
```

---

## 📊 核心命令 (推荐使用 main.py)

```bash
# 统一入口
python main.py scan              # 🔍 尾盘选股 (多因子增强版)
python main.py check --push      # 📋 持仓巡检 + 推送
python main.py premarket --push  # 📢 集合竞价预警 + 推送
python main.py update            # 📊 更新RPS数据
python main.py dashboard         # 📈 查看交易战绩
python main.py backtest          # 📉 策略回测

# 大盘风控 (新增 v2.3)
python main.py market            # 📊 查看大盘风控状态
python main.py market --sectors  # 查看热门板块TOP10

# 盘中实时监控 (v2.2)
python main.py monitor           # 📡 持续监控(直到收盘)
python main.py monitor --once    # 只检查一次
python main.py monitor --duration 60  # 监控60分钟
python main.py monitor --clear   # 清理提醒历史

# 虚拟持仓追踪 (新增 v2.3 策略验证)
python main.py virtual           # 🧪 运行策略验证监控
python main.py virtual --list    # 查看虚拟持仓
python main.py virtual --stats   # 查看统计报告
python main.py virtual --clear   # 清空重新开始

# 推荐效果统计 (v2.2)
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

## 🧪 虚拟持仓追踪模式 (模拟操作)

为了验证策略的长期有效性并协助新手熟悉操作，系统内置了**全自动虚拟持仓追踪**功能。

### 工作流程

1. **自动买入**：每日 `scan` 选出的标的会自动记录在 `data/virtual_positions.json` 中，作为虚拟持仓。
2. **实时监控**：系统会持续监控这些股票的盘中波动（MA5、ATR、最高点等）。
3. **卖点提醒**：一旦触发卖点策略，系统会通过钉钉发送【模拟卖出信号】，并自动记录在该笔交易中。
4. **统计战绩**：使用 `main.py virtual --stats` 可随时查看所有虚拟交易的胜率、盈亏比和分布。

### 卖点策略逻辑 (v2.3.1)

- **ATR 动态止损**：当价格跌破 `买入价 - 2 * ATR` 时强制离场。
- **移动止盈 (Trailing Stop)**：盈利超过 5% 后，若从最高点回撤超过 3%，则锁定利润离场。
- **分类策略**：
  - 核心标的：涨幅达 10% 止盈。
  - 潜力标的：涨幅达 5% 止盈一半。
  - 稳健标的：涨幅达 3% 落袋为安。
- **回撤保护**：任何浮盈超过 5% 的股票，若回撤超过 3% 自动触发保护信号。

---

## 📅 每日自动任务流程

系统已集成 `run_daily.sh` (Mac/Linux) 实现全自动化。建议定期或手动执行此脚本。

```
┌─────────────────────────────────────────────────────────────┐
│  每日收盘自动化流程 (建议 14:35 运行)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [1/4] 📊 更新 RPS 强度 ──► 获取市场最新动量排名               │
│           │                                                 │
│           ▼                                                 │
│  [2/4] 🔍 尾盘选股扫描 ──► 自动加入虚拟持仓 ──► 发送钉钉推荐    │
│           │                                                 │
│           ▼                                                 │
│  [3/4] 📋 持仓健康巡检 ──► 检查实盘风险 ──► 发送止损提醒       │
│           │                                                 │
│           ▼                                                 │
│  [4/4] 📡 虚拟持仓监控 ──► 实时追踪卖点 ──► 发送模拟操作信号    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**快速执行方式：**

```bash
source .venv/bin/activate && ./run_daily.sh
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

- **v2.5.1** (2026-01-09): 🔧 架构深度优化版 (当前版本)
  - **紧急 Bug 修复**
    - 修复 `realtime_monitor.py` 中 `kwargs` 未定义导致的运行时崩溃
    - 恢复 `safe_read_json`/`safe_write_json` 函数，修复提醒历史功能
  - **存储层统一**
    - `premarket.py` 集合竞价模块迁移至 SQLite 读取持仓
    - 移除对 `holdings.json` 的直接读取依赖
  - **性能与稳定性**
    - **尾盘数据延迟获取**：将 `get_tail_volume_ratio` 从主扫描循环移至前 10 名二次确认阶段，避免高频 API 调用导致 IP 封禁
    - **SQLite 写入优化**：添加 `PRAGMA synchronous=NORMAL`，提升实时监控频繁更新性能
    - **环境自检增强**：`main.py` 新增 SQLite 数据库读写权限检查，防止生产环境权限问题
  - **Market Breadth 渐进式风控**
    - 市场宽度 `≥8%`：正常交易
    - 市场宽度 `4%-8%`：单笔金额自动减半
    - 市场宽度 `<4%`：触发休眠模式，停止选股并推送通知
  - **尾盘吸筹判断增强**
    - 放量 + 当日涨价 = ✨ 真吸筹，评分加分
    - 放量 + 当日跌价 = ⚠️ 出货嫌疑，评分减分
    - 放量 + 滞涨 = 中性标记
  - **评级差异化参数**
    - Grade A (趋势核心)：ATR 2 倍，回撤容忍 -5%
    - Grade B (普通)：ATR 1.5 倍，回撤容忍 -3%
    - Grade C (稳健)：ATR 1.2 倍，回撤容忍 -2.5%
- **v2.4** (2026-01-08): 🛡️ 稳如泰山版
  - **架构稳定性升级**
    - **API 鲁棒性**: 引入 `tenacity` 实现指数退避重试，大幅降低网络波动导致的数据获取失败。
    - **并发写保护**: 引入跨进程文件锁，彻底解决多任务并发环境下 `JSON` 文件损坏的风险。
    - **未来函数修复**: 彻底修复 MA5 计算中的时间偏移风险，确保指标计算的绝对准确性。
    - **配置热重载**: 支持黑名单列表 (`blacklist.txt`) 无需重启即可动态生效。
  - **策略盈利能力优化**
    - **量价协同分析**: 新增五大形态识别（缩量蓄势、放量滞涨等），有效过滤诱多陷阱，通过缩量识别主力控盘。
    - **短期爆发因子**: 引入 **RPS20**，协同长周期趋势捕捉市场即时热门爆发点。
    - **板块效应统计**: 自动分析推荐股票中的板块共振，通过"抱团效应"进一步提升选股胜率。
    - **大盘总开关**: 完善行情风控逻辑，熊市自动触发"休眠模式"抑制不必要的开仓冲动。
- **v2.3.1** (2026-01-07): 🧠 策略大师版
  - **高级风控体系**
    - 引入 **ATR 动态止损** (CTA 基金级风控)，告别固定止损被洗盘
    - 新增 **休眠模式**：大盘跌破 20 日线自动停止选股，避开主跌浪
    - 新增 **移动止盈**：盈利超 5%后开启回撤保护
  - **资金管理系统**
    - 引入 **凯利公式**：根据胜率动态计算最佳仓位
    - 选股结果直接给出"建议买入股数"
  - **板块强弱滤网**
    - 只做全市场前 1/3 的强势板块
    - 避免"由于板块拖累而补跌"的情况
- **v2.3** (2026-01-07): 🎯 多因子策略版
  - 新增 **多因子综合评分系统**
    - 动量因子 (RPS) 30%
    - 资金流向因子 25%
    - 板块热度因子 25%
    - 估值因子 10%
    - 技术因子 10%
  - 新增 **大盘风控模块** (`market` 命令)
    - 指数均线判断趋势
    - 熊市自动停止/警告
    - 热门板块实时查看
  - 新增 **虚拟持仓追踪** (`virtual` 命令)
    - 自动将推荐加入虚拟持仓
    - 结合均线自动判断卖点
    - 自动统计胜率和收益
  - 选股升级为三轮筛选：基础条件 → MA5 趋势 → **多因子评分**
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

# 📈 AlphaHunter - 尾盘低吸选股系统

> 基于十年实战经验的量化选股工具，结合"尾盘低吸"策略 + RPS 强度评分

---

## 📁 项目结构

```
stock_trans/
│
├── 📄 scan.py              # 🔥 尾盘选股 (主入口)
├── 📄 update_rps.py        # 📊 更新 RPS 数据
├── 📄 backtest.py          # 📈 策略回测
├── 📄 scheduler.py         # ⏰ 定时任务
│
├── 📁 config/              # ⚙️ 配置文件
│   ├── __init__.py
│   └── settings.py         # 所有参数配置
│
├── 📁 src/                 # 🔧 核心模块
│   ├── __init__.py
│   ├── data_loader.py      # 数据获取
│   ├── indicators.py       # 技术指标
│   ├── strategy.py         # 选股策略
│   └── notifier.py         # 消息推送
│
├── 📁 data/                # 📦 数据存储
│   ├── rps/                # RPS 排名数据
│   └── history/            # 历史数据缓存
│
├── 📁 output/              # 📤 输出结果
│   ├── results/            # 选股结果
│   └── backtest/           # 回测报告
│
├── 📁 docs/                # 📚 文档
│   └── 策略思路.md
│
└── 📄 README.md
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

## 📊 核心命令

| 命令 | 说明 | 建议时间 |
|------|------|----------|
| `python update_rps.py` | 更新 RPS 数据 | 每天 17:00 (收盘后) |
| `python scan.py` | 尾盘选股 | 14:35 - 14:50 |
| `python position.py` | 持仓巡检 | 每天早盘/盘中 |
| `python backtest.py` | 策略回测 | 随时 |
| `python scheduler.py` | 启动定时任务 | 长期运行 |

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

### 平仓（记录盈亏）
```bash
# 使用当前价平仓
python position.py --close 600000

# 指定卖出价平仓
python position.py --close 600000,11.5
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

| 分类 | RPS 范围 | 操作建议 |
|------|----------|----------|
| ⭐ 趋势核心 | ≥ 90 | 可多拿几天，跌破 5 日线止损 |
| 🔥 潜力股 | 75-89 | 次日冲高卖一半，留一半观察 |
| 📊 稳健标的 | 40-74 | 次日冲高即走 |

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

- **v2.0** (2024-12-23): 重构项目结构，模块化设计
- **v1.0** (2024-12-23): 初始版本

---

## ⚠️ 免责声明

本工具仅供学习研究，不构成投资建议。
股市有风险，投资需谨慎。

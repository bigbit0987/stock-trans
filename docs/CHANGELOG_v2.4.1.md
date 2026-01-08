# AlphaHunter v2.4.1 更新日志

**发布日期**: 2026-01-08

本次更新基于深度代码审查，主要修复了潜在的并发安全问题，并增强了选股策略和止损机制。

---

## 🔴 高优先级修复

### 1. 文件并发安全问题修复

**问题描述**:

- `realtime_monitor.py` 和 `portfolio.py` 在读写 JSON 文件时缺乏线程/进程锁保护
- 如果 `run_realtime_monitor()` 在后台运行，同时手动执行 `main.py check`，可能导致 JSON 损坏

**修复方案**:

- 统一使用 `src/utils.py` 中的 `safe_read_json()` 和 `safe_write_json()` 函数
- 这些函数内置了线程锁 (`threading.Lock`) 和原子写入机制
- 可选支持跨进程文件锁 (`portalocker` 库，如已安装)

**涉及文件**:

- `src/tasks/realtime_monitor.py` - `load_alert_history()`, `save_alert_history()`
- `src/tasks/portfolio.py` - `load_holdings()`, `save_holdings()`

### 1.1 持仓巡检逻辑修复

**问题描述**:
`daily_check()` 中的条件判断逻辑存在问题，多个 `if` 语句没有使用 `elif` 正确链接，导致：

- ATR 止损触发后，后续的回撤检查会覆盖已设置的状态

**修复方案**:

- 使用 `if-elif-else` 确保条件判断互斥
- ATR 止损 > MA5 止损 > 回撤检查 > 止盈提醒 > 亏损关注

---

## 🟡 中优先级增强

### 2. RPS20 短周期指标和"弱转强"信号

**策略背景**:
参考 Qbot 的多周期 RPS 策略，单一 RPS120 可能错过短期爆发股。

**新增功能**:

- **RPS20**: 20 日短周期动量指标
- **弱转强信号**: RPS120 < 70 但 RPS20 > 90 的股票
  - 这类股票往往是新题材的领涨者
  - 比长周期走牛的股票更具爆发力

**配置项** (`config/settings.py`):

```python
STRATEGY = {
    # ...
    'rps_weak_to_strong': {
        'rps120_threshold': 70,     # RPS120 低于此值视为"弱"
        'rps20_breakthrough': 90,   # RPS20 突破此值视为"转强"
        'enabled': True,
    },
}
```

**涉及文件**:

- `src/tasks/updater.py` - 增加 RPS20 计算和弱转强检测

---

### 3. ATR 动态止损

**策略背景**:
固定百分比止损（如 -5%）对高波动股票太紧，对低波动股票太松。
ATR (平均真实波幅) 能让止损位自动适应股票的波动特性。

**新增功能**:

- 买入时自动计算 ATR 并存储止损位
- 持仓巡检时检查是否跌破 ATR 止损位
- ATR 止损优先级高于 MA5 止损

**计算公式**:

```
ATR止损位 = 买入价 - ATR × 倍数（默认 2 倍）
```

**涉及文件**:

- `src/tasks/portfolio.py` - `add_position()`, `daily_check()`, `_calculate_atr_stop_for_stock()`

---

### 4. 魔法数字配置化

**问题描述**:
多处硬编码的阈值分散在代码中，不便于调整。

**改进方案**:
将以下阈值移入 `config/settings.py`:

| 原硬编码                         | 新配置项                                                            | 位置                |
| -------------------------------- | ------------------------------------------------------------------- | ------------------- |
| `max_pnl > 3`                    | `REALTIME_MONITOR['drawdown_monitor_min_profit']`                   | realtime_monitor.py |
| `max_pnl > 10 and drawdown < -3` | `PORTFOLIO_CHECK['max_profit_threshold']`, `['drawdown_threshold']` | portfolio.py        |
| `pnl > 10`                       | `PORTFOLIO_CHECK['take_profit_alert']`                              | portfolio.py        |
| `pnl < -5`                       | `PORTFOLIO_CHECK['loss_attention_threshold']`                       | portfolio.py        |
| `0 < prev_pct < 5`               | `STRATEGY['prev_day_pct_min']`, `['prev_day_pct_max']`              | strategy.py         |

**新配置块**:

```python
PORTFOLIO_CHECK = {
    'max_profit_threshold': 10,     # 历史最高浮盈达到此值后 (%)
    'drawdown_threshold': -3,       # 回撤超过此值触发警报 (%)
    'take_profit_alert': 10,        # 当前盈利超过此值提醒 (%)
    'loss_attention_threshold': -5, # 亏损超过此值时标记需关注 (%)
}
```

---

## 📋 完整修改文件清单

| 文件                            | 修改类型  | 说明                                       |
| ------------------------------- | --------- | ------------------------------------------ |
| `src/tasks/realtime_monitor.py` | 修复      | 使用安全的 JSON 读写                       |
| `src/tasks/portfolio.py`        | 修复+增强 | 安全 JSON 读写 + ATR 止损                  |
| `src/tasks/updater.py`          | 增强      | RPS20 + 弱转强信号                         |
| `src/strategy.py`               | 优化      | 使用配置阈值                               |
| `config/settings.py`            | 新增      | PORTFOLIO_CHECK, rps_weak_to_strong 等配置 |

---

## 🧪 验证方法

```bash
# 1. 语法检查
python3 -m py_compile src/tasks/*.py src/strategy.py config/settings.py

# 2. 更新 RPS 数据（验证 RPS20 和弱转强检测）
python3 main.py update

# 3. 持仓巡检（验证 ATR 止损显示）
python3 main.py check

# 4. 添加测试持仓（验证 ATR 止损位计算）
python3 main.py add 600000 浦发银行 10.5 100
```

---

## 🔜 后续优化建议

1. **数据存储升级**: 将 JSON/CSV 迁移至 SQLite
2. **ML 二次打分**: 使用历史选股数据训练 LightGBM 模型
3. **情绪因子**: 集成新闻舆情分析
4. **Web 监控面板**: 使用 FastAPI + Vue3 构建实时仪表盘

---

## AlphaHunter v2.4.2 性能优化补丁

**发布日期**: 2026-01-08 (Hotfix)

### 🚀 核心性能优化

**1. 估值因子计算重构 (Critical)**

- **问题**: 原多因子评分中，估值计算逻辑会为每只候选股单独调用全市场 API (`ak.stock_zh_a_spot_em`)。如果有 50 只股票入选，会触发 50 次全市场数据拉取，导致极慢的速度和 API 限流风险。因性能原因，该功能之前被代码禁用（硬编码为 50 分）。
- **修复**: 重构为**一次性预加载**全市场估值数据，构建内存映射。查询复杂度从 O(N) 降为 O(1)。
- **效果**:
  - API 调用量大幅降低（N 次 -> 1 次）
  - **成功恢复了估值因子的有效性**（不再是无效的 50 分），现在的评分包含了真实的 PE/PB/市值 评估。

**2. 缓存清理健壮性**

- 修复了 `cache_manager` 在多进程环境下清理缓存可能导致的 `FileNotFoundError`。

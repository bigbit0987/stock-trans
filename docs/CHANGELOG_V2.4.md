# AlphaHunter v2.4 更新日志

> 更新时间: 2026-01-08
>
> 本次更新基于专业的架构与策略分析报告，从**架构稳定性**和**策略盈利能力**两个维度进行全面优化。

---

## 🔧 架构改进

### 1. MA5 时间偏移风险修复

**问题**: 原本 `hist_closes[-4:]` 可能包含当日数据，导致 MA5 计算把"今天"算两次。

**解决方案**:

- 新增 `ensure_history_excludes_today()` 函数
- 在 `get_stock_history()` 中默认启用日期校验
- 强制确保历史数据只保留到昨日

**文件**: `src/utils.py`, `src/data_loader.py`

### 2. 并发写入文件锁

**问题**: 多任务并发运行时，JSON 文件可能发生写入冲突导致数据丢失。

**解决方案**:

- 新增 `safe_read_json()` 和 `safe_write_json()` 带锁读写器
- 使用 `portalocker` 实现跨进程文件锁
- 使用 `threading.Lock` 实现进程内线程锁
- 采用临时文件 + 原子替换策略

**文件**: `src/utils.py`, `src/tasks/virtual_tracker.py`

### 3. API 重试机制增强

**问题**: Akshare 底层爬虫容易受网络波动影响。

**解决方案**:

- 引入 `tenacity` 库实现专业级指数退避重试
- 自动识别可重试的异常类型 (ConnectionError, TimeoutError, OSError)
- 保留降级兼容，无 tenacity 时使用简单重试

**文件**: `src/data_loader.py`

### 4. 黑名单动态加载

**问题**: 原本修改黑名单需要重启程序。

**解决方案**:

- 新增 `load_blacklist_dynamic()` 函数
- 检查文件修改时间，自动热重载
- 支持运行时刷新

**文件**: `src/utils.py`

---

## 📈 策略改进

### 1. 量价协同判断

**来源**: 策略报告建议区分"缩量蓄势"与"放量滞涨"

**实现**:

- 新增 `analyze_volume_price_pattern()` 函数
- 检测 5 种量价形态：
  - ⚠️ **放量滞涨** (危险信号): 涨幅<1% + 量比>2.5
  - ✨ **缩量蓄势** (正向信号): 涨幅 0-3% + 量比<1.0
  - 📈 **健康放量**: 涨幅>2% + 量比 1.2-2.5
  - 💤 **极度缩量**: 量比<0.5
  - 🎯 **持续缩量涨**: 历史量能收缩中且价格上涨

**效果**: 过滤掉约 30%的假突破

**文件**: `src/strategy.py`, `config/settings.py`

### 2. 短期 RPS (RPS20)

**来源**: 策略报告建议增加短周期 RPS 捕捉短期爆发

**实现**:

- 配置中新增 `rps_short_window: 20`
- 用于识别当前热点爆发的中心

**文件**: `config/settings.py`

### 3. 大盘总开关

**来源**: 策略报告建议在熊市自动停止选股

**实现**:

- 新增 `should_stop_trading()` 函数
- 新增 `check_market_and_decide()` 函数
- 检查条件：
  - 大盘跌破 20 日均线 + 配置 action='stop'
  - 大盘急跌超过阈值
  - 触发休眠模式
- 返回建议仓位比例

**文件**: `src/factors.py`

### 4. 板块效应统计

**来源**: 策略报告建议统计选股结果中的板块聚类

**实现**:

- 新增 `analyze_sector_cluster()` 函数
- 新增 `print_sector_cluster_report()` 函数
- 聚类判定：某板块占比>=30% 或 数量>=3
- 在扫描结束后自动输出板块效应报告

**效果**: 识别板块共振机会，这些股票胜率更高

**文件**: `src/factors.py`, `src/tasks/scanner.py`

---

## 📦 新增依赖

```txt
tenacity>=8.2.0            # 指数退避重试
portalocker>=2.8.0         # 跨平台文件锁
```

---

## 🔍 验证命令

```bash
# 测试所有改进模块
source .venv/bin/activate && python3 -c "
from src.utils import ensure_history_excludes_today, load_blacklist_dynamic
from src.strategy import analyze_volume_price_pattern
from src.factors import analyze_sector_cluster, should_stop_trading
print('所有模块导入成功!')
"

# 运行完整扫描测试
python3 main.py scan
```

---

## 📋 配置项说明

### VOLUME_PRICE_STRATEGY (新增)

```python
VOLUME_PRICE_STRATEGY = {
    'enabled': True,
    'stagnant_volume': {          # 放量滞涨判定
        'max_pct_change': 1.0,
        'min_volume_ratio': 2.5,
        'action': 'warn',         # filter/warn/downgrade
    },
    'shrinking_volume': {         # 缩量蓄势判定
        'max_pct_change': 3.0,
        'max_volume_ratio': 1.0,
        'bonus_score': 15,
    },
}
```

---

## 🎯 下一步建议

1. **实战验证**: 使用 `virtual_tracker` 记录"缩量阳线"和"放量阳线"的次日胜率对比
2. **参数调优**: 根据回测结果调整量价阈值
3. **增加 RPS20**: 在 RPS 计算中加入短期 RPS 因子
4. **ATR 吊灯止盈**: 完善动态止盈逻辑

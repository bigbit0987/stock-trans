#!/usr/bin/env python
"""
AlphaHunter - 尾盘低吸量化交易系统
统一命令行入口

使用方法:
    python main.py scan              # 尾盘选股
    python main.py check [--push]    # 持仓巡检
    python main.py update            # 更新RPS数据
    python main.py premarket [--push] # 集合竞价预警
    python main.py dashboard         # 查看交易战绩
    python main.py backtest          # 策略回测
    
    # 持仓管理
    python main.py add 代码 名称 价格 [数量]
    python main.py close 代码 [卖出价] [数量] [force]
    python main.py import [文件路径]
    python main.py list
    python main.py history
"""
import argparse
import sys
import os

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


def cmd_scan(args):
    """执行尾盘选股"""
    from scan import run_scan
    run_scan()


def cmd_check(args):
    """执行持仓巡检"""
    from position import daily_check
    alerts = daily_check()
    
    if args.push and alerts:
        try:
            from src.notifier import notify_position_alert
            notify_position_alert(alerts)
            print("\n📱 预警已推送到手机")
        except Exception as e:
            print(f"\n⚠️ 推送失败: {e}")


def cmd_update(args):
    """更新 RPS 数据"""
    from update_rps import update_rps_ranking
    update_rps_ranking()


def cmd_premarket(args):
    """集合竞价预警"""
    from premarket import check_premarket
    alerts = check_premarket()
    
    if args.push and alerts:
        try:
            from src.notifier import notify_premarket_alert
            notify_premarket_alert(alerts)
            print("\n📱 预警已推送到手机")
        except Exception as e:
            print(f"\n⚠️ 推送失败: {e}")


def cmd_dashboard(args):
    """查看交易战绩"""
    if args.web:
        print("正在启动 Streamlit 界面...")
        os.system(f"streamlit run dashboard.py")
    else:
        from dashboard import load_trade_history, print_summary
        df = load_trade_history()
        print_summary(df)


def cmd_backtest(args):
    """策略回测"""
    from backtest import run_backtest
    run_backtest()


def cmd_add(args):
    """添加持仓"""
    from position import add_position
    add_position(
        code=args.code,
        name=args.name,
        buy_price=args.price,
        quantity=args.quantity or 0,
        strategy=args.strategy or "STABLE"
    )


def cmd_close(args):
    """平仓"""
    from position import close_position
    close_position(
        code=args.code,
        sell_price=args.price,
        sell_quantity=args.quantity or 0,
        force=args.force
    )


def cmd_import(args):
    """导入持仓"""
    from position import import_from_csv
    import_from_csv(args.file)


def cmd_list(args):
    """列出持仓"""
    from position import list_holdings
    list_holdings()


def cmd_history(args):
    """查看交易历史"""
    import pandas as pd
    history_file = os.path.join(PROJECT_ROOT, "data", "trade_history.csv")
    if os.path.exists(history_file):
        df = pd.read_csv(history_file)
        print("\n📊 交易历史:")
        print("-" * 80)
        print(df.to_string(index=False))
        print("-" * 80)
        if '盈亏%' in df.columns:
            df['盈亏%'] = df['盈亏%'].astype(float)
            wins = len(df[df['盈亏%'] > 0])
            total = len(df)
            avg_pnl = df['盈亏%'].mean()
            print(f"\n📈 统计: 共{total}笔交易, 盈利{wins}笔, 胜率{wins/total*100:.1f}%, 平均收益{avg_pnl:.2f}%")
    else:
        print("📭 暂无交易历史")


def main():
    parser = argparse.ArgumentParser(
        description="🚀 AlphaHunter - 尾盘低吸量化交易系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py scan              # 执行尾盘选股
  python main.py check --push      # 持仓巡检并推送
  python main.py premarket --push  # 集合竞价预警并推送
  python main.py add 600000 浦发银行 10.5 1000
  python main.py close 600000 11.0
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # scan 命令
    subparsers.add_parser("scan", help="🔍 尾盘选股 (14:35-14:50)")
    
    # check 命令
    check_parser = subparsers.add_parser("check", help="📋 持仓巡检")
    check_parser.add_argument("--push", action="store_true", help="推送预警到手机")
    
    # update 命令
    subparsers.add_parser("update", help="📊 更新 RPS 数据")
    
    # premarket 命令
    premarket_parser = subparsers.add_parser("premarket", help="📢 集合竞价预警 (9:20-9:25)")
    premarket_parser.add_argument("--push", action="store_true", help="推送预警到手机")
    
    # dashboard 命令
    dashboard_parser = subparsers.add_parser("dashboard", help="📈 查看交易战绩")
    dashboard_parser.add_argument("--web", action="store_true", help="启动 Web 界面")
    
    # backtest 命令
    subparsers.add_parser("backtest", help="📉 策略回测")
    
    # add 命令
    add_parser = subparsers.add_parser("add", help="➕ 添加持仓")
    add_parser.add_argument("code", help="股票代码")
    add_parser.add_argument("name", help="股票名称")
    add_parser.add_argument("price", type=float, help="买入价格")
    add_parser.add_argument("quantity", type=int, nargs="?", help="买入数量")
    add_parser.add_argument("--strategy", choices=["RPS_CORE", "POTENTIAL", "STABLE"], help="策略类型")
    
    # close 命令
    close_parser = subparsers.add_parser("close", help="💰 平仓卖出")
    close_parser.add_argument("code", help="股票代码")
    close_parser.add_argument("price", type=float, nargs="?", help="卖出价格")
    close_parser.add_argument("quantity", type=int, nargs="?", help="卖出数量")
    close_parser.add_argument("--force", action="store_true", help="强制卖出(跳过T+1)")
    
    # import 命令
    import_parser = subparsers.add_parser("import", help="📥 从CSV导入持仓")
    import_parser.add_argument("file", nargs="?", help="CSV文件路径")
    
    # list 命令
    subparsers.add_parser("list", help="📋 列出所有持仓")
    
    # history 命令
    subparsers.add_parser("history", help="📜 查看交易历史")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    # 命令分发
    commands = {
        "scan": cmd_scan,
        "check": cmd_check,
        "update": cmd_update,
        "premarket": cmd_premarket,
        "dashboard": cmd_dashboard,
        "backtest": cmd_backtest,
        "add": cmd_add,
        "close": cmd_close,
        "import": cmd_import,
        "list": cmd_list,
        "history": cmd_history,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

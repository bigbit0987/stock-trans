#!/usr/bin/env python
"""
AlphaHunter - 尾盘低吸量化交易系统
统一命令行入口 (Unified Entry Point)
"""
import argparse
import sys
import os

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.utils import logger

def cmd_scan(args):
    """执行尾盘选股"""
    from src.tasks.scanner import run_scan
    run_scan()


def cmd_check(args):
    """执行持仓巡检"""
    from src.tasks.portfolio import daily_check
    alerts = daily_check()
    
    if args.push and alerts:
        try:
            from src.notifier import notify_position_alert
            notify_position_alert(alerts)
            logger.info("\n📱 预警已推送到手机")
        except Exception as e:
            logger.error(f"\n⚠️ 推送失败: {e}")


def cmd_update(args):
    """更新 RPS 数据"""
    from src.tasks.updater import run_updater
    run_updater()


def cmd_premarket(args):
    """集合竞价预警"""
    from src.tasks.premarket import check_premarket
    alerts = check_premarket()
    
    if args.push and alerts:
        try:
            from src.notifier import notify_premarket_alert
            notify_premarket_alert(alerts)
            logger.info("\n📱 预警已推送到手机")
        except Exception as e:
            logger.error(f"\n⚠️ 推送失败: {e}")


def cmd_dashboard(args):
    """查看交易战绩"""
    from src.tasks.dashboard import load_trade_history, print_summary, run_streamlit_app
    if args.web:
        run_streamlit_app()
    else:
        df = load_trade_history()
        print_summary(df)


def cmd_backtest(args):
    """策略回测"""
    from src.tasks.backtester import run_backtester
    run_backtester()


def cmd_add(args):
    """添加持仓"""
    from src.tasks.portfolio import add_position
    add_position(
        code=args.code,
        name=args.name,
        buy_price=args.price,
        quantity=args.quantity or 0,
        strategy=args.strategy or "STABLE"
    )


def cmd_close(args):
    """平仓"""
    from src.tasks.portfolio import close_position
    close_position(
        code=args.code,
        sell_price=args.price,
        sell_quantity=args.quantity or 0,
        force=args.force
    )


def cmd_import(args):
    """导入持仓"""
    from src.tasks.portfolio import import_from_csv
    import_from_csv(args.file)


def cmd_list(args):
    """列出持仓"""
    from src.tasks.portfolio import list_holdings
    list_holdings()


def cmd_history(args):
    """查看交易历史"""
    from src.tasks.dashboard import load_trade_history, print_summary
    df = load_trade_history()
    print_summary(df)


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
    
    # 选股
    subparsers.add_parser("scan", help="🔍 尾盘选股 (14:35-14:50)")
    
    # 巡检
    check_parser = subparsers.add_parser("check", help="📋 持仓巡检")
    check_parser.add_argument("--push", action="store_true", help="是否推送通知")
    
    # 更新 RPS
    subparsers.add_parser("update", help="📊 更新 RPS 数据")
    
    # 集合竞价
    pre_parser = subparsers.add_parser("premarket", help="📢 集合竞价预警 (9:20-9:25)")
    pre_parser.add_argument("--push", action="store_true", help="是否推送通知")
    
    # 战绩
    dash_parser = subparsers.add_parser("dashboard", help="📈 交易战绩总结")
    dash_parser.add_argument("--web", action="store_true", help="启动 Web 界面")
    
    # 回测
    subparsers.add_parser("backtest", help="📉 策略回测验证")
    
    # 管理命令
    add_parser = subparsers.add_parser("add", help="➕ 新增持仓记录")
    add_parser.add_argument("code", help="股票代码")
    add_parser.add_argument("name", help="股票名称")
    add_parser.add_argument("price", type=float, help="买入价格")
    add_parser.add_argument("quantity", type=int, nargs="?", help="数量")
    add_parser.add_argument("--strategy", choices=["RPS_CORE", "POTENTIAL", "STABLE"], help="策略")

    close_parser = subparsers.add_parser("close", help="💰 卖出结账")
    close_parser.add_argument("code", help="股票代码")
    close_parser.add_argument("price", type=float, nargs="?", help="成交价")
    close_parser.add_argument("quantity", type=int, nargs="?", help="数量")
    close_parser.add_argument("--force", action="store_true", help="强制忽略 T+1 限制")

    subparsers.add_parser("list", help="📋 查看当前所有持仓")
    subparsers.add_parser("history", help="📜 查看完整交易历史")
    
    imp_parser = subparsers.add_parser("import", help="📥 从选股结果导入持仓")
    imp_parser.add_argument("file", nargs="?", help="指定的 CSV 路径")

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    # 命令路由执行
    cmd_map = {
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
    
    if args.command in cmd_map:
        cmd_map[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

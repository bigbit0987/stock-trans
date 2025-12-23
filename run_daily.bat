@echo off
:: 切换代码页为 UTF-8 防止中文乱码
chcp 65001 >nul
setlocal
cd /d %~dp0

echo ==========================================
echo 🚀 AlphaHunter 一键启动程序 (收盘任务)
echo ==========================================
echo [%TIME%] [1/3] 正在更新 RPS 全市场排名数据...
python main.py update

echo.
echo [%TIME%] [2/3] 正在执行尾盘选股扫描...
:: 如果需要推送到手机，可以手动加上 --push
python main.py scan --push

echo.
echo [%TIME%] [3/3] 正在执行持仓健康巡检...
python main.py check --push

echo.
echo ==========================================
echo ✅ 今日任务处理完成！
echo ==========================================
pause

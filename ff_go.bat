@echo off
rem ff_go 的 Windows 批处理入口：双击即可进入选择菜单。
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo 没有找到 python，请先安装 Python 3.9 或更高版本。
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

python -m ff_go %*
set EXITCODE=%errorlevel%
if not "%EXITCODE%"=="0" (
    echo.
    pause
)
endlocal & exit /b %EXITCODE%

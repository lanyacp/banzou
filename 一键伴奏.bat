@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "python\pythonw.exe" (
    echo.
    echo   找不到运行环境，请确认整个文件夹已完整解压后再运行。
    echo.
    pause
    exit /b
)

start "" "%~dp0python\pythonw.exe" "%~dp0app\main.py"
exit

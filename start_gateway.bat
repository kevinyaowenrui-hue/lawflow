@echo off
chcp 65001 >nul
title LawFlow 智律工作台 - 服务控制台
cd /d "%~dp0"

echo ======================================================================
echo           LawFlow 智律工作台 (LawFlow Workspace) 控制台启动器
echo ======================================================================

set "PY_EXE="
if exist "%USERPROFILE%\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" (
    set "PY_EXE=%USERPROFILE%\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
)

if "%PY_EXE%"=="" (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        if not "%%i"=="%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\python.exe" (
            set "PY_EXE=%%i"
            goto :found_py
        )
    )
)

:found_py
if "%PY_EXE%"=="" set "PY_EXE=python"

echo [信息] 使用 Python 解释器: %PY_EXE%
echo [信息] 正在启动网关服务 (http://127.0.0.1:5221)...
echo [提示] 保持此窗口开启即可持续运行后端服务；关闭此窗口将停止服务。
echo.

"%PY_EXE%" gateway/main.py

pause

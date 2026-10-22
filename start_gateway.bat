@echo off
chcp 65001 >nul
title LawFlow 智律工作台 - 服务控制台
cd /d "%~dp0"

echo ======================================================================
echo           LawFlow 智律工作台 (LawFlow Workspace) 控制台启动器
echo ======================================================================

set "PY_EXE="

REM 1) 项目内虚拟环境
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
)

REM 2) 环境变量 LAWFLOW_PYTHON
if "%PY_EXE%"=="" if defined LAWFLOW_PYTHON (
    if exist "%LAWFLOW_PYTHON%" set "PY_EXE=%LAWFLOW_PYTHON%"
)

REM 3) PATH 中的 python（跳过 WindowsApps 占位）
if "%PY_EXE%"=="" (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        echo %%i | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
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

"%PY_EXE%" -m uvicorn gateway.main:app --host 127.0.0.1 --port 5221

pause

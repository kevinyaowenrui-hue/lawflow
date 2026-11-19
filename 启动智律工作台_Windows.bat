@echo off
chcp 65001 >nul
title LawFlow 智律工作台 (中国执业律师本地安全版)
echo ======================================================================
echo   LawFlow 智律工作台 — 本地化优先 (Local-First) 正在启动...
echo   所有案卷与当事人数据均保留在本机，不上传任何第三方公有云库
echo ======================================================================
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)
start "" http://127.0.0.1:5221
python -m uvicorn gateway.main:app --host 127.0.0.1 --port 5221
pause

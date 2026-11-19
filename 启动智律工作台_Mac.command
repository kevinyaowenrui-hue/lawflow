#!/bin/bash
cd "$(dirname "$0")"
echo "======================================================================"
echo "  LawFlow 智律工作台 — 本地化优先 (Local-First) 正在启动..."
echo "  监听地址: http://127.0.0.1:5221"
echo "======================================================================"
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi
(sleep 2 && open "http://127.0.0.1:5221" 2>/dev/null || xdg-open "http://127.0.0.1:5221" 2>/dev/null) &
python3 -m uvicorn gateway.main:app --host 127.0.0.1 --port 5221

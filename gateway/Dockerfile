# 构建上下文须为仓库根目录：
#   docker build -f gateway/Dockerfile -t lawflow:test .
#   或 docker compose build（compose 已将 context 设为 "."）
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    fontconfig \
    ca-certificates \
    curl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/share/fonts/truetype/custom /app/storage /app/templates /app/frontend /app/fonts

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || \
    pip install --no-cache-dir -r requirements.txt

COPY gateway/ /app/gateway/
COPY frontend/ /app/frontend/
COPY templates/ /app/templates/
COPY data/ /app/data/

ENV PYTHONUNBUFFERED=1
ENV LAWFLOW_STORAGE_DIR=/app/storage
ENV LAWFLOW_FRONTEND_DIR=/app/frontend
ENV LAWFLOW_TEMPLATES_DIR=/app/templates
ENV LAWFLOW_FONTS_DIR=/usr/share/fonts/truetype/custom
ENV GATEWAY_HOST=0.0.0.0
ENV GATEWAY_PORT=5221

EXPOSE 5221

# 挂载 fonts/ 后刷新字体缓存，再启动网关
CMD ["sh", "-c", "fc-cache -f 2>/dev/null || true; exec uvicorn gateway.main:app --host 0.0.0.0 --port 5221"]

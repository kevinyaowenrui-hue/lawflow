FROM python:3.11-slim

# 安装中文公文支持与基础图形依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    fontconfig \
    ca-certificates \
    curl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 创建法院中文字体挂载目录与应用路径
RUN mkdir -p /usr/share/fonts/truetype/custom /app/storage /app/templates /app/frontend

WORKDIR /app

# 安装 Python 核心依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || \
    pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . /app/gateway/
COPY ./main.py /app/main.py

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV GATEWAY_PORT=8000
ENV GATEWAY_HOST=0.0.0.0

EXPOSE 8000

CMD ["python", "main.py"]

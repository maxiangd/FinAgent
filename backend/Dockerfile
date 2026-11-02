# 后端镜像：构建上下文为项目根目录（需要根目录的 requirements.txt）
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./

# 国内网络访问 pypi.org 常超时；默认用清华镜像，需要时用 --build-arg 覆盖
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

COPY backend/ ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# 任务状态保存在进程内，必须单 worker 运行；多实例需要把任务表也迁移到外部存储
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

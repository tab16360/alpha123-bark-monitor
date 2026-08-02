FROM python:3.12-slim

# Install tzdata for timezone configuration & cleanup apt cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && echo "Asia/Shanghai" > /etc/timezone \
    && ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 -i ${PIP_INDEX_URL} --upgrade pip && \
    pip install --no-cache-dir --default-timeout=120 -i ${PIP_INDEX_URL} -r requirements.txt

# Copy application source code
COPY app/ ./app/
COPY README.md pytest.ini docker-entrypoint.sh ./

# Create non-root user and set permissions
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data /data/debug && \
    chmod +x /app/docker-entrypoint.sh && \
    chown -R appuser:appuser /app /data

EXPOSE 18181

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import os, urllib.request; port=os.getenv('HEALTH_SERVER_PORT', '18181'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health')" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "app.main", "run"]

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

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/
COPY README.md pytest.ini ./

# Create non-root user and data directory
RUN useradd -m -u 1000 appuser && \
    mkdir -p /data /data/debug && \
    chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1

CMD ["python", "-m", "app.main", "run"]

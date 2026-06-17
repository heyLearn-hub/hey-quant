FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY bin ./bin
COPY docs ./docs
COPY scripts ./scripts

RUN python -m pip install --upgrade pip \
    && python -m pip install .

RUN mkdir -p /app/data/cache /app/outputs /app/logs \
    && chmod +x /app/bin/quant-ai-local

EXPOSE 8765

ENTRYPOINT ["python", "-m", "quant_ai_system.cli"]
CMD ["serve", "--config", "config/default.yaml", "--out", "outputs/latest_report.html", "--host", "0.0.0.0", "--port", "8765"]


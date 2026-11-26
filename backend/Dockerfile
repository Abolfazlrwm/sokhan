FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY sokhan ./sokhan
COPY alembic ./alembic

RUN pip install --no-cache-dir .

RUN useradd --system --uid 1000 --create-home appuser \
    && mkdir -p /data/audio \
    && chown -R appuser:appuser /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "sokhan.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple

COPY hermes/requirements.lock .
RUN pip install --no-cache-dir --timeout 60 --retries 10 --index-url "${PIP_INDEX_URL}" -r requirements.lock

COPY hermes/app/ /app/app/
COPY runtimes/hermes/skills/ /app/skills/
COPY runtimes/hermes/scripts/purge-telemetry.py /app/scripts/purge-telemetry.py
COPY db/schema.sql /app/db/schema.sql
COPY db/alembic.ini /app/db/alembic.ini
COPY db/migrations/ /app/db/migrations/

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=3)" || exit 1

CMD ["python", "-m", "app.main"]

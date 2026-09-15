FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple

COPY hermes/requirements.txt .
RUN pip install --no-cache-dir --timeout 60 --retries 10 --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY hermes/app/ /app/app/
COPY runtimes/hermes/skills/ /app/skills/
COPY db/schema.sql /app/db/schema.sql
COPY db/alembic.ini /app/db/alembic.ini
COPY db/migrations/ /app/db/migrations/

CMD ["python", "-m", "app.main"]

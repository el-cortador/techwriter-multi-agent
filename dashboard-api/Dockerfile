FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple

COPY dashboard-api/requirements.txt .
RUN pip install --no-cache-dir --timeout 60 --retries 10 --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY dashboard-api/app ./app
COPY db/schema.sql /app/db/schema.sql

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

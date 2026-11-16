# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only the application code and its migrations, never the whole repository.
COPY app/ app/
COPY migrations/ migrations/

RUN useradd --system --no-create-home appuser
USER appuser

EXPOSE 8000
CMD ["python", "-m", "app.main"]

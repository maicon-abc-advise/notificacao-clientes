# Imagem da API (Python 3.12 enxuto).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

COPY pyproject.toml .
COPY app ./app

RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8000

# Servidor ASGI (FastAPI).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

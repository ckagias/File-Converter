FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg libreoffice poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app/ ./app/

RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --create-home appuser && \
    mkdir -p /app/uploads /app/outputs && \
    chown -R appuser:appgroup /app/uploads /app/outputs /home/appuser

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
FROM python:3.11-slim

WORKDIR /app

# Runtime deps needed by this project (ffmpeg/ffprobe are required).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
COPY requirements.lock.txt .
COPY requirements.optional-diarization.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=12 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read(); sys.exit(0)"

CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]


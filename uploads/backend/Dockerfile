FROM python:3.11-slim-bookworm

WORKDIR /app

# Runtime/build deps needed by this project:
# - ffmpeg/ffprobe: video/audio processing
# - pkg-config + libav*-dev: kept for compatibility with audio/video Python deps
# - build-essential/gcc/g++/git: required by some Python packages during install
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
        gcc \
        g++ \
        git \
        pkg-config \
        python3-dev \
        libavformat-dev \
        libavcodec-dev \
        libavdevice-dev \
        libavutil-dev \
        libavfilter-dev \
        libswscale-dev \
        libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
COPY requirements.lock.txt .
COPY requirements.optional-diarization.txt .

RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

COPY backend ./backend

RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=12 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read(); sys.exit(0)"

CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]

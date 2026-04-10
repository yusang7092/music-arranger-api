FROM python:3.11-slim

# 시스템 의존성 (LilyPond + ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    lilypond \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1단계: CPU 전용 PyTorch 먼저 설치 (CUDA 없이 → 용량 1/8)
RUN pip install --no-cache-dir \
    torch==2.2.0 torchaudio==2.2.0 \
    --index-url https://download.pytorch.org/whl/cpu

# 2단계: 나머지 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

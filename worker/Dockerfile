FROM python:3.12-slim

# ffmpeg binary — installed system-wide so ffmpeg-python can find it
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app/ into /app/worker/ so Python resolves "worker.*" imports correctly
COPY app/ ./worker/

CMD ["python", "-m", "worker.worker"]

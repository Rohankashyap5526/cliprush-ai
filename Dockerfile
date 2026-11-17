# Build the React UI, then package it with the FastAPI API and FFmpeg.
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_BASE=""
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000 \
    CLIPRUSH_DATA_DIR=/tmp/cliprush-data
WORKDIR /app
# fonts-liberation: caption/hook font (without any font, burned-in captions can silently fail on slim images)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates fonts-liberation fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY --from=frontend-build /frontend/dist ./frontend/dist/
RUN useradd --create-home --uid 10001 cliprush \
    && mkdir -p /tmp/cliprush-data/uploads /tmp/cliprush-data/clips \
    && chown -R cliprush:cliprush /tmp/cliprush-data /app
USER cliprush
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','10000'), timeout=4)"
CMD ["python", "-u", "-m", "app.run"]

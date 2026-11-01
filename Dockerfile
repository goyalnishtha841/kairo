# Kairo -- one container, one process: FastAPI serves both the API and the built frontend from
# the same origin, so there's no CORS setup to do in production. CPU only, no GPU needed.
#
# Build:  docker build -t kairo .
# Run:    docker run -p 8000:8000 --env-file .env kairo
# (GROQ_API_KEY / ANTHROPIC_API_KEY are optional -- the copilot falls back to a deterministic
# rules engine with no key at all, so this runs with zero configuration too.)

# ---- stage 1: build the frontend -------------------------------------------------------------
FROM node:22-slim AS webbuild
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- stage 2: the actual app -------------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

# libgl1/libglib2.0-0: mediapipe + opencv need these on a headless (GUI-less) Debian base, or
# `import cv2` fails with a missing libGL.so.1. ffmpeg: imageio-ffmpeg bundles its own static
# binary at first use, but having the system one too costs little and avoids a first-request
# download stall.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY . .
# outputs/, data/raw/ etc. are excluded by .dockerignore; this just lays the built frontend on top.
COPY --from=webbuild /app/web/dist ./web/dist

# Sample recordings, baked into the image so every visitor sees them and they survive restarts
# (Render's free disk is wiped on each deploy). Built by scripts/build_sample_data.py and attached
# to a GitHub Release; bump the tag to ship a new data set. Set SAMPLE_DATA_URL="" to build without it.
ARG SAMPLE_DATA_URL=https://github.com/goyalnishtha841/kairo/releases/download/sample-data-v2/kairo-sample-data-v2.tar.gz
RUN if [ -n "$SAMPLE_DATA_URL" ]; then \
      python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/sample.tar.gz')" "$SAMPLE_DATA_URL" \
      && tar -xzf /tmp/sample.tar.gz -C /app && rm /tmp/sample.tar.gz \
      && echo "sample data: $(ls /app/outputs | wc -l) entries"; \
    fi

ENV PORT=8000
EXPOSE 8000
# shell form so ${PORT} expands -- Render (and most PaaS hosts) inject PORT at runtime and expect
# the container to bind to it, which isn't always 8000.
CMD uvicorn server.app:app --host 0.0.0.0 --port ${PORT}

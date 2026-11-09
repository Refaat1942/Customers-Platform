# ---------- 1) build the website ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2) API + serve the built website ----------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/data FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist /app/frontend/dist
RUN useradd -r -u 1000 appuser && mkdir -p /data && chown appuser /data
USER appuser
EXPOSE 1100
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:1100/api/health')"
# one worker: uploads in progress, login limits and the results cache live in this process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1100", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-keep-alive", "75"]

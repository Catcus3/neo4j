FROM python:3.11-slim

# Make Python logs unbuffered; no .pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Minimal OS deps (certs + timezone data)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better caching), then copy app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run will set PORT; default to 8080 for local sanity
ENV PORT=8080

# Use the module runner so we don't depend on a PATH binary
CMD ["python","-m","uvicorn","main:app","--host","0.0.0.0","--port","8080"]

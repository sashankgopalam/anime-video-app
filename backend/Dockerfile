# Backend image for hosting on Render (or any Docker host).
# Bundles ffmpeg since it's not a pip package and Render's native runtime
# doesn't include it.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects its own $PORT at runtime; main.py already reads it
# (defaults to 8000 for local/other hosts).
EXPOSE 8000
CMD ["python3", "main.py"]

FROM python:3.11-slim

# ffmpeg decodes audio streams; Deno is the JS runtime yt-dlp requires to run
# YouTube's JS challenge solver (remote_components "ejs") — without it the
# solver is silently skipped and stream resolution can fail or be throttled.
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh \
  && deno --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "bot.py"]

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs curl unzip \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp only auto-uses Deno (not Node.js) to solve YouTube's signature
# challenges unless told otherwise, so install it explicitly.
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh
ENV PATH="/usr/local/bin:${PATH}"
# Fail the build loudly here instead of finding out at runtime, days later,
# from a cryptic yt-dlp warning.
RUN deno --version && node --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=7860
EXPOSE 7860

CMD ["python3", "app.py"]

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Tegucigalpa

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    tzdata \
    dos2unix \
  && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
  && echo $TZ > /etc/timezone \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN dos2unix /app/entrypoint.sh \
  && chmod +x /app/entrypoint.sh \
  && mkdir -p /app/staticfiles /app/media /app/logs

EXPOSE 8000

CMD ["/app/entrypoint.sh"]

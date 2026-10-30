FROM python:3.15-slim-trixie

RUN apt-get update \
 && apt-get install -y --no-install-recommends nmap iproute2 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .

ENV DB_PATH=/data/lanscanner.db \
    WEB_PORT=8080 \
    SCAN_TARGETS=auto \
    SCAN_INTERVAL_MINUTES=60 \
    PYTHONUNBUFFERED=1

VOLUME /data
EXPOSE 8080
CMD ["python", "main.py"]

FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/pdf_api /tmp/pdf_serve

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pdf_api.py .

EXPOSE 8000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 8 --worker-class gthread --timeout 420 pdf_api:app"]

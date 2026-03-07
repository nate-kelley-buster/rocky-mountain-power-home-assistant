FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY sidecar/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m playwright install --with-deps chromium

COPY custom_components /app/custom_components
COPY sidecar /app/sidecar

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "sidecar.app:app", "--host", "0.0.0.0", "--port", "8080"]

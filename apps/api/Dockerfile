# syntax=docker/dockerfile:1.4
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PROMPTGUARD_DASHBOARD_STATIC_DIR=/opt/promptguard/dashboard

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        tesseract-ocr \
        tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m venv /opt/venvs/api \
    && /opt/venvs/api/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/venvs/api/bin/python -m pip install --no-cache-dir -r requirements.txt

COPY requirements-paddle-gpu.txt ./
RUN python -m venv /opt/venvs/paddle \
    && /opt/venvs/paddle/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/venvs/paddle/bin/python -m pip install --no-cache-dir -r requirements-paddle-gpu.txt

COPY requirements-torch-gpu.txt ./
RUN python -m venv /opt/venvs/torch \
    && /opt/venvs/torch/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/venvs/torch/bin/python -m pip install --no-cache-dir -r requirements-torch-gpu.txt

COPY . .
COPY --from=dashboard . /opt/promptguard/dashboard

EXPOSE 8000

CMD ["/opt/venvs/api/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

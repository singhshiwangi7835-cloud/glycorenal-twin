# GlycoRenal Twin: one image runs the API or either dashboard (see docker-compose.yml)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp1 is needed by XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# train Model 1 at build time so containers start instantly
RUN python scripts/train.py

EXPOSE 8000 8501 8502
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

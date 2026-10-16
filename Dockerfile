# GlycoRenal Twin: one image runs the API, the Streamlit app, or both (MODE=api|ui|all).
#   docker compose up --build           -> API on :8000 and app on :8501 (two containers)
#   docker run -p 7860:7860 IMAGE       -> both in one container on :7860 (Hugging Face Spaces)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# libgomp1: XGBoost; curl: health checks
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# trained models are committed in models/; build the synthetic demo CGM traces used by the seed
RUN python scripts/build_synthetic_cohort.py

# run as a normal user (uid 1000, as Hugging Face Spaces expects) who can write the database
RUN useradd -m -u 1000 twin && mkdir -p /app/data/db && chown -R twin:twin /app
USER twin
ENV DATABASE_URL=sqlite:////app/data/db/twin.db \
    MODE=all \
    PORT=7860

EXPOSE 8000 8501 7860
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -sf http://127.0.0.1:8000/health || exit 1
CMD ["bash", "deploy/start.sh"]

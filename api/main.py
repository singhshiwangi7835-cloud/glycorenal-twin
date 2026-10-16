"""FastAPI backend for GlycoRenal Twin.

Run locally:  uvicorn api.main:app --reload     Docs: http://localhost:8000/docs
On startup: create tables, seed demo data if the database is empty, and start the daily job
that re-runs every patient's twin (DKD risk is re-run on new labs, medicine changes, or daily).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from sqlmodel import Session

from api.routers import alerts, auth, ehr, patients, treatments, twin
from config.settings import DEV_JWT_SECRET, get_settings
from src.db.seed import seed_demo
from src.db.session import engine, init_db, is_empty
from src.twin.engine import run_all

log = logging.getLogger("glycorenal")


def daily_job() -> None:
    with Session(engine) as s:
        n = run_all(s)
    log.info("Daily twin re-run done for %d patients", n)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    init_db()
    if s.auto_seed and is_empty():
        log.warning("Database is empty: seeding demo data (about 20 s) ...")
        seed_demo()
    if s.jwt_secret == DEV_JWT_SECRET:
        log.warning("JWT_SECRET is not set in .env: using an insecure development secret.")
    scheduler = None
    if s.scheduler_enabled:
        scheduler = BackgroundScheduler(timezone=s.timezone)
        scheduler.add_job(daily_job, "cron", hour=2, minute=0, id="daily_twin")
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="GlycoRenal Twin API",
    description="Digital twin for T2DM glycaemic control and DKD prevention. "
                "Prototype: decision support only, not for clinical use.",
    version="0.3.0",
    lifespan=lifespan,
)
for r in (auth, patients, twin, treatments, alerts, ehr):
    app.include_router(r.router)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "version": app.version}

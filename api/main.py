"""FastAPI backend for GlycoRenal Twin.

Run locally:  uvicorn api.main:app --reload     Docs: http://localhost:8000/docs
On startup: create tables, seed demo data if the database is empty, create today's medicine
doses, start the live sensor simulator for SIM_AUTOSTART patients, and start background jobs:
  - every 5 min: pending doses older than 2 h -> missed
  - every minute: post-meal glucose spikes
  - every 10 min: "sensor disconnected" check
  - 00:05 daily: tomorrow's doses; 02:00 daily: full twin re-run for every patient
The /docs page uses a local copy of Swagger UI (api/static/swagger, MIT licence), so it works
offline and where the CDN is blocked.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from api.routers import admin, alerts, auth, devices, ehr, llm, meals, patients, reminders, treatments, twin
from config.settings import DEV_JWT_SECRET, get_settings
from src.alerts.engine import check_stale_sensors
from src.db.models import Patient
from src.db.seed import seed_demo
from src.db.session import engine, init_db, is_empty
from src.ingestion import simulator
from src.meals.engine import compute_spikes
from src.reminders.engine import ensure_dose_events, mark_missed
from src.twin.engine import run_all

log = logging.getLogger("glycorenal")


def _job(fn, label: str):
    def run() -> None:
        try:
            with Session(engine) as s:
                fn(s)
        except Exception:  # noqa: BLE001  (a failed job must not stop the scheduler)
            log.exception("background job %s failed", label)
    return run


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    init_db()
    if s.auto_seed and is_empty():
        log.warning("Database is empty: seeding demo data (about 20 s) ...")
        seed_demo()
    if s.jwt_secret == DEV_JWT_SECRET:
        log.warning("JWT_SECRET is not set in .env: using an insecure development secret.")
    scheduler, runner = None, None
    if s.scheduler_enabled:
        with Session(engine) as session:
            ensure_dose_events(session)
            mark_missed(session)
            for pid in [p.strip() for p in s.sim_autostart.split(",") if p.strip()]:
                if session.get(Patient, pid):
                    simulator.start(session, pid)
        scheduler = BackgroundScheduler(timezone=s.timezone)
        scheduler.add_job(_job(mark_missed, "missed doses"), "interval", minutes=5, id="missed")
        scheduler.add_job(_job(compute_spikes, "meal spikes"), "interval", minutes=1, id="spikes")
        scheduler.add_job(_job(check_stale_sensors, "stale sensors"), "interval", minutes=10, id="stale")
        scheduler.add_job(_job(ensure_dose_events, "dose events"), "cron", hour=0, minute=5, id="doses")
        scheduler.add_job(_job(run_all, "daily twin"), "cron", hour=2, minute=0, id="daily_twin")
        scheduler.start()
        runner = simulator.Runner(engine, s.sim_speed_seconds)
        runner.start()
    yield
    if runner:
        runner.stop()
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="GlycoRenal Twin API",
    description="Digital twin for T2DM glycaemic control and DKD prevention. "
                "Prototype: decision support only, not for clinical use.",
    version="0.5.0",
    lifespan=lifespan,
    docs_url=None,  # served below from local files
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
for r in (auth, patients, twin, treatments, alerts, ehr, devices, reminders, meals, llm, admin):
    app.include_router(r.router)


@app.get("/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url=app.openapi_url, title=f"{app.title} - docs",
                               swagger_js_url="/static/swagger/swagger-ui-bundle.js",
                               swagger_css_url="/static/swagger/swagger-ui.css",
                               swagger_favicon_url="")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": app.title, "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "version": app.version}

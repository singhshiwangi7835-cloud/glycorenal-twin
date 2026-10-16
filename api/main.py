"""FastAPI backend for GlycoRenal Twin.

Run locally:  uvicorn api.main:app --reload     Docs: http://localhost:8000/docs
On startup: create tables, seed demo data if the database is empty, and start the daily job
that re-runs every patient's twin (DKD risk is re-run on new labs, medicine changes, or daily).
The /docs page uses a local copy of Swagger UI (api/static/swagger, MIT licence), so it works
offline and where the CDN is blocked.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
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
    docs_url=None,  # served below from local files
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
for r in (auth, patients, twin, treatments, alerts, ehr):
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

"""FastAPI backend for GlycoRenal Twin.

Run locally:  uvicorn api.main:app --reload     Docs: http://localhost:8000/docs
On startup the database tables are created and, if the database is empty, demo data is seeded.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routers import auth, legacy
from config.settings import DEV_JWT_SECRET, get_settings
from src.db.seed import seed_demo
from src.db.session import init_db, is_empty

log = logging.getLogger("glycorenal")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    init_db()
    if s.auto_seed and is_empty():
        seed_demo()
        log.warning("Database was empty: demo users and patients created.")
    if s.jwt_secret == DEV_JWT_SECRET:
        log.warning("JWT_SECRET is not set in .env: using an insecure development secret.")
    yield


app = FastAPI(
    title="GlycoRenal Twin API",
    description="Digital twin for T2DM glycaemic control and DKD prevention. "
                "Prototype: decision support only, not for clinical use.",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(auth.router)
app.include_router(legacy.router)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "version": app.version}

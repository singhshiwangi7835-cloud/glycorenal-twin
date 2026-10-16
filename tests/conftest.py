"""Test setup: use a throwaway SQLite database so tests never touch data/twin.db."""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp()) / "test_twin.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["SCHEDULER_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from api.main import app
    with TestClient(app) as c:  # runs startup: creates tables + seeds demo data
        yield c


def login(client, username, password):
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

import pytest

from src.auth.security import hash_password, verify_password
from tests.conftest import login


def test_password_hashing():
    h = hash_password("doctor123")
    assert h != "doctor123"
    assert verify_password("doctor123", h)
    assert not verify_password("wrong", h)


@pytest.mark.parametrize("username,password,role", [
    ("admin", "admin123", "admin"),
    ("dr.mehta", "doctor123", "doctor"),
    ("ramesh", "patient123", "patient"),
    ("sunita", "patient123", "patient"),
])
def test_demo_logins(client, username, password, role):
    me = client.get("/auth/me", headers=login(client, username, password)).json()
    assert me["role"] == role


def test_ramesh_is_linked_to_his_patient_record(client):
    me = client.get("/auth/me", headers=login(client, "ramesh", "patient123")).json()
    assert me["patient_id"] == "IND-0042" and me["language"] == "hi"


def test_wrong_password_and_missing_token(client):
    r = client.post("/auth/login", data={"username": "ramesh", "password": "nope"})
    assert r.status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_only_admin_can_list_users(client):
    assert client.get("/auth/users", headers=login(client, "dr.mehta", "doctor123")).status_code == 403
    users = client.get("/auth/users", headers=login(client, "admin", "admin123")).json()
    assert len(users) == 12  # admin + doctor + 10 patients


def test_admin_creates_user(client):
    h = login(client, "admin", "admin123")
    r = client.post("/auth/users", headers=h, json={
        "username": "dr.rao", "password": "doctor123", "role": "doctor", "full_name": "Dr. Rao"})
    assert r.status_code == 200
    login(client, "dr.rao", "doctor123")
    bad = client.post("/auth/users", headers=h, json={
        "username": "x", "password": "y", "role": "patient", "patient_id": "NOPE"})
    assert bad.status_code == 422

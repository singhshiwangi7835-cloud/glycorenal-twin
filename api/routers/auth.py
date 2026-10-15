"""Login and user management: POST /auth/login, GET /auth/me, POST /auth/users (admin)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import Session, select

from src.auth.security import (create_token, current_user, hash_password, require_roles,
                               verify_password)
from src.db.models import ROLES, Patient, User
from src.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    full_name: str
    language: str
    patient_id: Optional[str] = None


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    full_name: str = ""
    language: str = "en"
    patient_id: Optional[str] = None


def _out(u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username, role=u.role, full_name=u.full_name,
                   language=u.language, patient_id=u.patient_id)


@router.post("/login", response_model=LoginOut)
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == form.username.strip())).first()
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return LoginOut(access_token=create_token(user), user=_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return _out(user)


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_roles("admin"))])
def create_user(body: UserCreate, session: Session = Depends(get_session)):
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if session.exec(select(User).where(User.username == body.username)).first():
        raise HTTPException(409, "username already exists")
    if body.role == "patient" and (not body.patient_id or not session.get(Patient, body.patient_id)):
        raise HTTPException(422, "patient users need an existing patient_id")
    user = User(username=body.username, password_hash=hash_password(body.password),
                role=body.role, full_name=body.full_name, language=body.language,
                patient_id=body.patient_id)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _out(user)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_roles("admin"))])
def list_users(session: Session = Depends(get_session)):
    return [_out(u) for u in session.exec(select(User).order_by(User.role, User.username))]

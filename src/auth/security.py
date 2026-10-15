"""Passwords (bcrypt) and login tokens (JWT), plus FastAPI role checks.

Uses the `bcrypt` library directly: passlib 1.7 is unmaintained and breaks with bcrypt >= 4.1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import Session

from config.settings import get_settings
from src.db.models import User
from src.db.session import get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("ascii"))
    except ValueError:
        return False


def create_token(user: User) -> str:
    s = get_settings()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "patient_id": user.patient_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expire_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def current_user(token: str = Depends(oauth2_scheme),
                 session: Session = Depends(get_session)) -> User:
    s = get_settings()
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in or session expired",
                                 headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = int(jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])["sub"])
    except (JWTError, KeyError, ValueError):
        raise unauthorized
    user = session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_roles(*roles: str):
    """Dependency factory: `Depends(require_roles("doctor", "admin"))`."""
    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Needs role: {', '.join(roles)}")
        return user
    return check


def can_see_patient(user: User, patient_id: str) -> bool:
    """Patients see only their own record; doctors and admins see all (for the prototype)."""
    return user.role in ("doctor", "admin") or user.patient_id == patient_id

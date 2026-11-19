"""Login and shared authentication, role, and resource-owner checks."""
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from db import get_db
from models import User
from schemas import Token
from security import DUMMY_HASH, create_access_token, password_hash, read_access_token

SessionDep = Annotated[Session, Depends(get_db)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)
router = APIRouter(prefix="/auth", tags=["auth"])


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    valid = password_hash.verify(password, user.password_hash if user else DUMMY_HASH)
    return user if user is not None and valid else None


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: SessionDep):
    user = authenticate(db, form.username, form.password)
    if user is None:
        raise unauthorized("Incorrect email or password")
    return Token(access_token=create_access_token(user.id),
                 expires_in=settings.access_token_minutes * 60)


def get_optional_user(
    token: Annotated[str | None, Depends(oauth2_scheme)], db: SessionDep,
) -> User | None:
    if token is None:
        return None
    try:
        user_id = read_access_token(token)
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid or expired token") from None
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("Invalid or expired token")
    return user


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise unauthorized("Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def can_access_student(user: User, student_id: int) -> bool:
    return user.role == "admin" or user.student_id == student_id


def require_student_access(user: User, student_id: int) -> None:
    if not can_access_student(user, student_id):
        raise HTTPException(403, "You can access only your own student profile")

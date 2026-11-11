"""Shared FastAPI dependencies — database session, authentication, RBAC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.config import settings
from xfox.db.engine import get_session_factory
from xfox.db.models import UserRow
from xfox.db.repo import users as users_repo
from xfox.domain.enums import Permission, Role
from xfox.domain.permissions import role_has

COOKIE_NAME = "xfox_session"


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------


async def get_db() -> AsyncSession:
    """Yield a session; commit on success, roll back on error."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def create_access_token(user: UserRow) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": datetime.now(tz=UTC) + timedelta(days=settings.session_days),
        "iat": datetime.now(tz=UTC),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_session") from exc


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


# ---------------------------------------------------------------------------
# Current user & permissions
# ---------------------------------------------------------------------------

_cookie_dep = APIKeyCookie(name=COOKIE_NAME, auto_error=False)


async def get_current_user(
    request: Request, db: DbDep, token: str | None = Depends(_cookie_dep)
) -> UserRow:
    if token is None:
        token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    payload = decode_access_token(token)
    user = await users_repo.get_by_id(db, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user_inactive")
    return user


CurrentUser = Annotated[UserRow, Depends(get_current_user)]


def require(permission: Permission):
    """Route dependency enforcing a single permission for the current user."""

    async def _checker(user: CurrentUser) -> UserRow:
        if not role_has(Role(user.role), permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")
        return user

    return _checker


def require_admin() -> UserRow:
    return Depends(require(Permission.USERS_MANAGE))

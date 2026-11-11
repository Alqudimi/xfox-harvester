"""Authentication endpoints — bootstrap, login, logout, profile, password."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from pwdlib import PasswordHash

from xfox.api.deps import (
    CurrentUser,
    DbDep,
    clear_session_cookie,
    create_access_token,
    set_session_cookie,
)
from xfox.db.repo import users as users_repo
from xfox.domain.enums import EventCategory, EventLevel, EventType, Role
from xfox.domain.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    SetupRequest,
    UserPublic,
)
from xfox.engine.events import emit_event

router = APIRouter(prefix="/api/auth", tags=["auth"])

_password_hasher = PasswordHash.recommended()

# Simple in-memory brute-force guard: {(ip, username): [monotonic timestamps]}
_ATTEMPTS: dict[tuple[str, str], list[float]] = {}
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(password, hashed)
    except Exception:
        return False


def _register_failure(ip: str, username: str) -> None:
    key = (ip, username)
    now = time.monotonic()
    attempts = [t for t in _ATTEMPTS.get(key, []) if now - t < _WINDOW_SECONDS]
    attempts.append(now)
    _ATTEMPTS[key] = attempts


def _is_blocked(ip: str, username: str) -> bool:
    key = (ip, username)
    now = time.monotonic()
    return len([t for t in _ATTEMPTS.get(key, []) if now - t < _WINDOW_SECONDS]) >= _MAX_ATTEMPTS


def _clear_failures(ip: str, username: str) -> None:
    _ATTEMPTS.pop((ip, username), None)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/bootstrap-status")
async def bootstrap_status(db: DbDep) -> dict:
    """Frontend uses this to choose between the setup screen and the login form."""
    count = await users_repo.count_users(db)
    return {"initialized": count > 0}


@router.post("/setup", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def setup(payload: SetupRequest, db: DbDep) -> UserPublic:
    """Create the first admin account. Rejected once any user exists."""
    if await users_repo.count_users(db) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_initialized")

    user = await users_repo.create_user(
        db,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=Role.ADMIN.value,
        display_name=payload.display_name,
    )
    await emit_event(
        db,
        type=EventType.USER_CREATED,
        level=EventLevel.SUCCESS,
        category=EventCategory.SECURITY,
        message=f"Admin account '{user.username}' created (first-run setup)",
        params={"role": Role.ADMIN.value},
    )
    await db.flush()
    return UserPublic.model_validate(user)


@router.post("/login", response_model=UserPublic)
async def login(
    payload: LoginRequest, request: Request, response: Response, db: DbDep
) -> UserPublic:
    ip = _client_ip(request)
    if _is_blocked(ip, payload.username):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts")

    user = await users_repo.get_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        _register_failure(ip, payload.username)
        await emit_event(
            db,
            type=EventType.USER_LOGIN_FAILED,
            level=EventLevel.WARNING,
            category=EventCategory.SECURITY,
            message=f"Failed login for '{payload.username}' from {ip}",
        )
        await db.flush()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_credentials")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account_disabled")

    _clear_failures(ip, payload.username)
    await users_repo.touch_last_login(db, user.id)
    token = create_access_token(user)
    set_session_cookie(response, token)
    await emit_event(
        db,
        type=EventType.USER_LOGIN,
        level=EventLevel.INFO,
        category=EventCategory.SECURITY,
        message=f"User '{user.username}' logged in from {ip}",
    )
    await db.flush()
    return UserPublic.model_validate(user)


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response) -> MessageResponse:
    clear_session_cookie(response)
    return MessageResponse(message="logged_out")


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, db: DbDep
) -> MessageResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current_password_incorrect")
    user.password_hash = hash_password(payload.new_password)
    await db.flush()
    await emit_event(
        db,
        type=EventType.PASSWORD_CHANGED,
        level=EventLevel.INFO,
        category=EventCategory.SECURITY,
        message=f"Password changed for '{user.username}'",
    )
    await db.flush()
    return MessageResponse(message="password_changed")

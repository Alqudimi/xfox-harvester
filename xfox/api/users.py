"""User management endpoints (admin only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from xfox.api.auth import hash_password
from xfox.api.deps import DbDep, require
from xfox.db.models import UserRow
from xfox.db.repo import users as users_repo
from xfox.domain.enums import EventCategory, EventLevel, EventType, Permission, Role
from xfox.domain.schemas import MessageResponse, UserCreateRequest, UserPublic, UserUpdateRequest
from xfox.engine.events import emit_event

router = APIRouter(prefix="/api/users", tags=["users"])

AdminUser = Annotated[UserRow, Depends(require(Permission.USERS_MANAGE))]


@router.get("", response_model=list[UserPublic])
async def list_users(db: DbDep, _admin: AdminUser) -> list[UserPublic]:
    rows = await users_repo.list_users(db)
    return [UserPublic.model_validate(row) for row in rows]


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreateRequest, db: DbDep, _admin: AdminUser) -> UserPublic:
    if await users_repo.get_by_username(db, payload.username) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")

    user = await users_repo.create_user(
        db,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        display_name=payload.display_name,
    )
    await emit_event(
        db,
        type=EventType.USER_CREATED,
        level=EventLevel.SUCCESS,
        category=EventCategory.SECURITY,
        message=f"User '{user.username}' created with role {user.role}",
        params={"role": user.role},
    )
    await db.flush()
    return UserPublic.model_validate(user)


@router.patch("/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: int, payload: UserUpdateRequest, db: DbDep, _admin: AdminUser
) -> UserPublic:
    user = await users_repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")

    updates = payload.model_dump(exclude_unset=True)
    if "password" in updates:
        password = updates.pop("password")
        if password:
            user.password_hash = hash_password(password)
    if "role" in updates and updates["role"] is not None:
        if user.id == _admin.id and Role(updates["role"]) != Role.ADMIN:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_demote_self")
        user.role = Role(updates["role"]).value
    if "is_active" in updates and updates["is_active"] is not None:
        if user.id == _admin.id and not updates["is_active"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_deactivate_self")
        user.is_active = updates["is_active"]
    if "display_name" in updates and updates["display_name"] is not None:
        user.display_name = updates["display_name"]

    await emit_event(
        db,
        type=EventType.USER_UPDATED,
        level=EventLevel.INFO,
        category=EventCategory.SECURITY,
        message=f"User '{user.username}' updated",
    )
    await db.flush()
    return UserPublic.model_validate(user)


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(user_id: int, db: DbDep, _admin: AdminUser) -> MessageResponse:
    user = await users_repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    if user.id == _admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_delete_self")

    username = user.username
    await users_repo.delete_user(db, user)
    await emit_event(
        db,
        type=EventType.USER_DELETED,
        level=EventLevel.WARNING,
        category=EventCategory.SECURITY,
        message=f"User '{username}' deleted",
    )
    await db.flush()
    return MessageResponse(message="user_deleted")

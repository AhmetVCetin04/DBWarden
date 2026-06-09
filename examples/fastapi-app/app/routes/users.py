from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from config import primary
from app.models import User
from app.schemas import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


# ── Session injection ──────────────────────────────────────────
# The `session: primary.async_session` parameter is a FastAPI
# dependency annotation.  Behind the scenes, this:
#   1. Opens a new async database session from the connection pool
#      configured in config.py
#   2. Passes it to the route handler
#   3. Commits (or rolls back on exception) when the handler returns
#   4. Closes the session and returns it to the pool
#
# No manual session management, no middleware, no context vars.
# The session is auto-rolled-back if an exception escapes the handler.


@router.get("/", response_model=list[UserResponse])
async def list_users(
    session: primary.async_session,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
):
    stmt = select(User).offset(skip).limit(limit)
    if active_only:
        stmt = stmt.where(User.is_active is True)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, session: primary.async_session):
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(user_data: UserCreate, session: primary.async_session):
    user = User(**user_data.model_dump())
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="User with this email or username already exists",
        )
    await session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    session: primary.async_session,
):
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail="Email or username already taken",
        )
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session: primary.async_session):
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()

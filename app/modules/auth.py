from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.exceptions import BadRequestError, ConflictError, UnauthorizedError
from app.models.user import User

# --- Schemas ---


class RegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str
    phone: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# --- Service ---


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise ConflictError("Email already registered")

    user = User(
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        phone=data.phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, data: LoginRequest) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


async def refresh_tokens(db: AsyncSession, data: RefreshRequest) -> TokenResponse:
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid token type")

    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or disabled")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


# --- Router ---

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await register_user(db, data)
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await login_user(db, data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await refresh_tokens(db, data)

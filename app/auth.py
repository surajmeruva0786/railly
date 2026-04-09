from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, Header

from app.config import settings
from app.exceptions import UnauthorizedError


# --- Password Hashing ---

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# --- JWT ---

def create_access_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid token")


# --- Auth Dependency ---

async def get_current_user_id(authorization: str = Header(...)) -> UUID:
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Invalid authorization header")
    token = authorization[7:]
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")
    return UUID(payload["sub"])

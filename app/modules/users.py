from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.exceptions import NotFoundError
from app.models.user import SavedPassenger, User, UserPreference

# --- Schemas ---


class UserResponse(BaseModel):
    id: UUID
    email: str
    phone: str | None
    full_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None


class PreferencesResponse(BaseModel):
    preferred_class: str | None
    preferred_berth: str | None
    home_station_code: str | None
    notifications_enabled: bool

    model_config = {"from_attributes": True}


class UpdatePreferencesRequest(BaseModel):
    preferred_class: str | None = None
    preferred_berth: str | None = None
    home_station_code: str | None = None
    notifications_enabled: bool | None = None


class PassengerResponse(BaseModel):
    id: UUID
    full_name: str
    age: int
    gender: str
    berth_preference: str | None
    is_primary: bool

    model_config = {"from_attributes": True}


class CreatePassengerRequest(BaseModel):
    full_name: str
    age: int
    gender: str
    berth_preference: str | None = None
    is_primary: bool = False


# --- Service ---


async def get_user(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found")
    return user


async def get_or_create_preferences(db: AsyncSession, user_id: UUID) -> UserPreference:
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = UserPreference(user_id=user_id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)
    return prefs


# --- Router ---

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_profile(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_user(db, user_id)


@router.put("/me", response_model=UserResponse)
async def update_profile(
    data: UpdateProfileRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user(db, user_id)
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.phone is not None:
        user.phone = data.phone
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me/preferences", response_model=PreferencesResponse)
async def get_preferences(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await get_or_create_preferences(db, user_id)


@router.put("/me/preferences", response_model=PreferencesResponse)
async def update_preferences(
    data: UpdatePreferencesRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    prefs = await get_or_create_preferences(db, user_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)
    await db.commit()
    await db.refresh(prefs)
    return prefs


@router.get("/me/passengers", response_model=list[PassengerResponse])
async def list_passengers(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedPassenger).where(SavedPassenger.user_id == user_id)
    )
    return result.scalars().all()


@router.post("/me/passengers", response_model=PassengerResponse, status_code=201)
async def add_passenger(
    data: CreatePassengerRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    passenger = SavedPassenger(user_id=user_id, **data.model_dump())
    db.add(passenger)
    await db.commit()
    await db.refresh(passenger)
    return passenger


@router.delete("/me/passengers/{passenger_id}", status_code=204)
async def delete_passenger(
    passenger_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedPassenger).where(
            SavedPassenger.id == passenger_id, SavedPassenger.user_id == user_id
        )
    )
    passenger = result.scalar_one_or_none()
    if not passenger:
        raise NotFoundError("Passenger not found")
    await db.delete(passenger)
    await db.commit()

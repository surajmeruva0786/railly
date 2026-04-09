import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(15), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    preferences: Mapped["UserPreference | None"] = relationship(back_populates="user")
    passengers: Mapped[list["SavedPassenger"]] = relationship(back_populates="user")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    preferred_class: Mapped[str | None] = mapped_column(String(5), nullable=True)
    preferred_berth: Mapped[str | None] = mapped_column(String(10), nullable=True)
    home_station_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="preferences")


class SavedPassenger(Base):
    __tablename__ = "saved_passengers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(150))
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(1))  # M, F, O
    berth_preference: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="passengers")

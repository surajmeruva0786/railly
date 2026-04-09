import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pnr_number: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    train_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trains.id"))
    journey_date: Mapped[date] = mapped_column(Date)
    from_station_code: Mapped[str] = mapped_column(String(10))
    to_station_code: Mapped[str] = mapped_column(String(10))
    class_type: Mapped[str] = mapped_column(String(5))
    quota: Mapped[str] = mapped_column(String(5), default="GN")
    booking_status: Mapped[str] = mapped_column(String(20))  # CONFIRMED, RAC, WAITLISTED, CANCELLED
    total_fare_inr: Mapped[float] = mapped_column(Numeric(10, 2))
    payment_status: Mapped[str] = mapped_column(String(15), default="PAID")
    booked_at: Mapped[datetime] = mapped_column(server_default=func.now())
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    passengers: Mapped[list["BookingPassenger"]] = relationship(back_populates="booking")


class BookingPassenger(Base):
    __tablename__ = "booking_passengers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    passenger_name: Mapped[str] = mapped_column(String(150))
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(1))
    berth_preference: Mapped[str | None] = mapped_column(String(10), nullable=True)
    current_status: Mapped[str] = mapped_column(String(20))  # CNF, RAC, WL, CAN
    coach_label: Mapped[str | None] = mapped_column(String(10), nullable=True)
    seat_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    berth_type: Mapped[str | None] = mapped_column(String(12), nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="passengers")

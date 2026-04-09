"""Bookings module — simulated ticket booking with PNR generation."""

import random
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user_id
from app.database import get_db
from app.exceptions import BadRequestError, NotFoundError
from app.models.booking import Booking, BookingPassenger
from app.models.train import Train

# --- Schemas ---


class PassengerInput(BaseModel):
    name: str
    age: int
    gender: str  # M, F, O
    berth_preference: str | None = None


class CreateBookingRequest(BaseModel):
    train_number: str
    journey_date: date
    from_station: str
    to_station: str
    class_type: str
    quota: str = "GN"
    passengers: list[PassengerInput]


class PassengerResponse(BaseModel):
    passenger_name: str
    age: int
    gender: str
    current_status: str
    coach_label: str | None
    seat_number: int | None
    berth_type: str | None

    model_config = {"from_attributes": True}


class BookingResponse(BaseModel):
    id: UUID
    pnr_number: str
    train_number: str | None = None
    journey_date: date
    from_station_code: str
    to_station_code: str
    class_type: str
    quota: str
    booking_status: str
    total_fare_inr: float
    payment_status: str
    passengers: list[PassengerResponse]

    model_config = {"from_attributes": True}


# --- Service ---

# Simple fare table (per km per class)
FARE_PER_KM = {
    "SL": 0.35, "3A": 0.85, "2A": 1.25, "1A": 2.10, "CC": 1.00, "2S": 0.20,
}


def generate_pnr() -> str:
    return str(random.randint(1000000000, 9999999999))


async def create_booking(
    db: AsyncSession, user_id: UUID, data: CreateBookingRequest
) -> Booking:
    # Get train
    result = await db.execute(select(Train).where(Train.number == data.train_number))
    train = result.scalar_one_or_none()
    if not train:
        raise NotFoundError(f"Train {data.train_number} not found")

    if not data.passengers:
        raise BadRequestError("At least one passenger required")

    # Calculate fare (simplified)
    distance = train.total_distance_km or 500
    rate = FARE_PER_KM.get(data.class_type.upper(), 0.50)
    fare_per_person = max(round(distance * rate, 2), 50)
    total_fare = fare_per_person * len(data.passengers)

    booking = Booking(
        user_id=user_id,
        pnr_number=generate_pnr(),
        train_id=train.id,
        journey_date=data.journey_date,
        from_station_code=data.from_station.upper(),
        to_station_code=data.to_station.upper(),
        class_type=data.class_type.upper(),
        quota=data.quota.upper(),
        booking_status="CONFIRMED",
        total_fare_inr=total_fare,
        payment_status="PAID",
    )
    db.add(booking)
    await db.flush()

    for p in data.passengers:
        db.add(
            BookingPassenger(
                booking_id=booking.id,
                passenger_name=p.name,
                age=p.age,
                gender=p.gender,
                berth_preference=p.berth_preference,
                current_status="CNF",
            )
        )

    await db.commit()
    await db.refresh(booking)

    # Reload with passengers
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking.id)
        .options(selectinload(Booking.passengers))
    )
    return result.scalar_one()


async def get_user_bookings(db: AsyncSession, user_id: UUID) -> list[Booking]:
    result = await db.execute(
        select(Booking)
        .where(Booking.user_id == user_id)
        .options(selectinload(Booking.passengers))
        .order_by(Booking.booked_at.desc())
    )
    return result.scalars().all()


async def cancel_booking(db: AsyncSession, user_id: UUID, booking_id: UUID) -> Booking:
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id, Booking.user_id == user_id)
        .options(selectinload(Booking.passengers))
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError("Booking not found")

    if booking.booking_status == "CANCELLED":
        raise BadRequestError("Booking already cancelled")

    booking.booking_status = "CANCELLED"
    booking.cancelled_at = datetime.now(timezone.utc)
    for p in booking.passengers:
        p.current_status = "CAN"

    await db.commit()
    await db.refresh(booking)
    return booking


# --- Router ---

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post("/", response_model=BookingResponse, status_code=201)
async def create(
    data: CreateBookingRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    booking = await create_booking(db, user_id, data)
    return BookingResponse(
        id=booking.id,
        pnr_number=booking.pnr_number,
        journey_date=booking.journey_date,
        from_station_code=booking.from_station_code,
        to_station_code=booking.to_station_code,
        class_type=booking.class_type,
        quota=booking.quota,
        booking_status=booking.booking_status,
        total_fare_inr=float(booking.total_fare_inr),
        payment_status=booking.payment_status,
        passengers=[PassengerResponse.model_validate(p) for p in booking.passengers],
    )


@router.get("/", response_model=list[BookingResponse])
async def list_bookings(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bookings = await get_user_bookings(db, user_id)
    return [
        BookingResponse(
            id=b.id,
            pnr_number=b.pnr_number,
            journey_date=b.journey_date,
            from_station_code=b.from_station_code,
            to_station_code=b.to_station_code,
            class_type=b.class_type,
            quota=b.quota,
            booking_status=b.booking_status,
            total_fare_inr=float(b.total_fare_inr),
            payment_status=b.payment_status,
            passengers=[PassengerResponse.model_validate(p) for p in b.passengers],
        )
        for b in bookings
    ]


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel(
    booking_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    booking = await cancel_booking(db, user_id, booking_id)
    return BookingResponse(
        id=booking.id,
        pnr_number=booking.pnr_number,
        journey_date=booking.journey_date,
        from_station_code=booking.from_station_code,
        to_station_code=booking.to_station_code,
        class_type=booking.class_type,
        quota=booking.quota,
        booking_status=booking.booking_status,
        total_fare_inr=float(booking.total_fare_inr),
        payment_status=booking.payment_status,
        passengers=[PassengerResponse.model_validate(p) for p in booking.passengers],
    )

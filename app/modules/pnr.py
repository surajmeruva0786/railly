"""PNR status lookup module."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.exceptions import NotFoundError
from app.models.booking import Booking, BookingPassenger
from app.models.train import Train

# --- Schemas ---


class PNRPassengerStatus(BaseModel):
    name: str
    status: str
    coach: str | None
    seat: int | None
    berth: str | None


class PNRResponse(BaseModel):
    pnr_number: str
    train_number: str
    train_name: str
    journey_date: str
    from_station: str
    to_station: str
    class_type: str
    booking_status: str
    passengers: list[PNRPassengerStatus]


# --- Service ---


async def check_pnr(db: AsyncSession, pnr_number: str) -> PNRResponse:
    result = await db.execute(
        select(Booking)
        .where(Booking.pnr_number == pnr_number)
        .options(selectinload(Booking.passengers))
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise NotFoundError(f"PNR {pnr_number} not found")

    # Get train info
    train_result = await db.execute(select(Train).where(Train.id == booking.train_id))
    train = train_result.scalar_one()

    return PNRResponse(
        pnr_number=booking.pnr_number,
        train_number=train.number,
        train_name=train.name,
        journey_date=str(booking.journey_date),
        from_station=booking.from_station_code,
        to_station=booking.to_station_code,
        class_type=booking.class_type,
        booking_status=booking.booking_status,
        passengers=[
            PNRPassengerStatus(
                name=p.passenger_name,
                status=p.current_status,
                coach=p.coach_label,
                seat=p.seat_number,
                berth=p.berth_type,
            )
            for p in booking.passengers
        ],
    )


# --- Router ---

router = APIRouter(prefix="/pnr", tags=["PNR"])


@router.get("/{pnr_number}", response_model=PNRResponse)
async def pnr_status(pnr_number: str, db: AsyncSession = Depends(get_db)):
    return await check_pnr(db, pnr_number)

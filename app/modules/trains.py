from datetime import date, time
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.exceptions import BadRequestError, NotFoundError
from app.models.train import Train, TrainScheduleStop

# --- Schemas ---


class TrainBrief(BaseModel):
    id: UUID
    number: str
    name: str
    train_type: str
    source_station_code: str
    destination_station_code: str
    runs_on_days: str
    has_pantry: bool

    model_config = {"from_attributes": True}


class ScheduleStopResponse(BaseModel):
    station_code: str
    stop_sequence: int
    arrival_time: time | None
    departure_time: time | None
    halt_minutes: int
    distance_from_source_km: int
    day_offset: int

    model_config = {"from_attributes": True}


class TrainDetailResponse(TrainBrief):
    total_distance_km: int | None
    schedule: list[ScheduleStopResponse]


class TrainSearchResult(BaseModel):
    train: TrainBrief
    departure_time: time | None
    arrival_time: time | None
    from_stop_sequence: int
    to_stop_sequence: int
    distance_km: int


# --- Service ---

DAY_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}  # Mon=0 ... Sun=6


async def search_trains(
    db: AsyncSession, from_code: str, to_code: str, journey_date: date
) -> list[TrainSearchResult]:
    """Find all trains that pass through both from_code and to_code in the right order."""
    # Get trains that stop at both stations
    from_stops = select(TrainScheduleStop.train_id, TrainScheduleStop.stop_sequence).where(
        TrainScheduleStop.station_code == from_code.upper()
    ).subquery()

    to_stops = select(TrainScheduleStop.train_id, TrainScheduleStop.stop_sequence).where(
        TrainScheduleStop.station_code == to_code.upper()
    ).subquery()

    stmt = (
        select(Train)
        .join(from_stops, Train.id == from_stops.c.train_id)
        .join(to_stops, Train.id == to_stops.c.train_id)
        .where(from_stops.c.stop_sequence < to_stops.c.stop_sequence)
        .where(Train.is_active == True)
        .options(selectinload(Train.schedule))
    )

    result = await db.execute(stmt)
    trains = result.scalars().unique().all()

    # Filter by day of week
    day_index = journey_date.weekday()  # Mon=0
    results = []
    for train in trains:
        if train.runs_on_days[day_index] != "1":
            continue

        from_stop = next(s for s in train.schedule if s.station_code == from_code.upper())
        to_stop = next(s for s in train.schedule if s.station_code == to_code.upper())
        distance = to_stop.distance_from_source_km - from_stop.distance_from_source_km

        results.append(TrainSearchResult(
            train=TrainBrief.model_validate(train),
            departure_time=from_stop.departure_time,
            arrival_time=to_stop.arrival_time,
            from_stop_sequence=from_stop.stop_sequence,
            to_stop_sequence=to_stop.stop_sequence,
            distance_km=distance,
        ))

    return sorted(results, key=lambda r: r.departure_time or time(0, 0))


async def get_train_detail(db: AsyncSession, number: str) -> Train:
    result = await db.execute(
        select(Train)
        .where(Train.number == number)
        .options(selectinload(Train.schedule))
    )
    train = result.scalar_one_or_none()
    if not train:
        raise NotFoundError(f"Train {number} not found")
    return train


# --- Router ---

router = APIRouter(prefix="/trains", tags=["Trains"])


@router.get("/search", response_model=list[TrainSearchResult])
async def search(
    from_station: str = Query(..., alias="from", description="Source station code"),
    to_station: str = Query(..., alias="to", description="Destination station code"),
    date: date = Query(..., description="Journey date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    return await search_trains(db, from_station, to_station, date)


@router.get("/{number}", response_model=TrainDetailResponse)
async def get_train(number: str, db: AsyncSession = Depends(get_db)):
    return await get_train_detail(db, number)

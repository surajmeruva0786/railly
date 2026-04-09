"""Chart module — reservation chart status and coach-wise passenger list."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.exceptions import NotFoundError
from app.models.chart import ChartEntry, ReservationChart
from app.models.train import Train

# --- Schemas ---


class ChartEntryResponse(BaseModel):
    coach_label: str
    seat_number: int
    berth_type: str
    passenger_name: str
    age: int
    gender: str
    from_station_code: str
    to_station_code: str
    booking_status: str
    pnr_number: str

    model_config = {"from_attributes": True}


class ChartStatusResponse(BaseModel):
    train_number: str
    train_name: str
    journey_date: date
    chart_sequence: int
    status: str
    prepared_at: str | None
    total_passengers: int
    entries: list[ChartEntryResponse]


# --- Service ---


async def get_chart(
    db: AsyncSession, train_number: str, journey_date: date
) -> ChartStatusResponse:
    # Get train
    result = await db.execute(select(Train).where(Train.number == train_number))
    train = result.scalar_one_or_none()
    if not train:
        raise NotFoundError(f"Train {train_number} not found")

    # Get chart
    chart_result = await db.execute(
        select(ReservationChart)
        .where(
            ReservationChart.train_id == train.id,
            ReservationChart.journey_date == journey_date,
        )
        .options(selectinload(ReservationChart.entries))
        .order_by(ReservationChart.chart_sequence.desc())
    )
    chart = chart_result.scalars().first()

    if not chart:
        return ChartStatusResponse(
            train_number=train.number,
            train_name=train.name,
            journey_date=journey_date,
            chart_sequence=0,
            status="NOT_PREPARED",
            prepared_at=None,
            total_passengers=0,
            entries=[],
        )

    return ChartStatusResponse(
        train_number=train.number,
        train_name=train.name,
        journey_date=journey_date,
        chart_sequence=chart.chart_sequence,
        status=chart.status,
        prepared_at=str(chart.prepared_at) if chart.prepared_at else None,
        total_passengers=len(chart.entries),
        entries=[ChartEntryResponse.model_validate(e) for e in chart.entries],
    )


async def get_chart_by_coach(
    db: AsyncSession, train_number: str, journey_date: date, coach_label: str
) -> ChartStatusResponse:
    full_chart = await get_chart(db, train_number, journey_date)
    full_chart.entries = [
        e for e in full_chart.entries if e.coach_label == coach_label.upper()
    ]
    full_chart.total_passengers = len(full_chart.entries)
    return full_chart


# --- Router ---

router = APIRouter(prefix="/charts", tags=["Charts"])


@router.get("/{train_number}/{journey_date}", response_model=ChartStatusResponse)
async def chart_status(
    train_number: str,
    journey_date: date,
    db: AsyncSession = Depends(get_db),
):
    return await get_chart(db, train_number, journey_date)


@router.get(
    "/{train_number}/{journey_date}/coach/{coach_label}",
    response_model=ChartStatusResponse,
)
async def chart_by_coach(
    train_number: str,
    journey_date: date,
    coach_label: str,
    db: AsyncSession = Depends(get_db),
):
    return await get_chart_by_coach(db, train_number, journey_date, coach_label)

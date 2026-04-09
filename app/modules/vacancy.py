"""THE CORE MODULE — Segment-aware vacant seat finder.

Given a train, date, and your journey segment (from → to), this finds which seats
are vacant and classifies them:

- FULLY_VACANT: No one booked for any part of your journey. Sit worry-free.
- BECOMES_VACANT: Passenger deboards mid-journey. Seat frees up at a station.
- VACANT_UNTIL: Passenger boards mid-journey. Seat is free only until that station.
"""

from datetime import date, time
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import BadRequestError, NotFoundError
from app.models.coach import Seat, TrainCoach
from app.models.seat_map import SeatMap
from app.models.train import Train, TrainScheduleStop

# --- Schemas ---


class StationInfo(BaseModel):
    code: str
    name: str | None = None
    time: str | None = None


class VacantSeat(BaseModel):
    seat_number: int
    berth_type: str
    compartment: int


class BecomesVacantSeat(BaseModel):
    seat_number: int
    berth_type: str
    compartment: int
    vacant_from_station: StationInfo
    note: str


class VacantUntilSeat(BaseModel):
    seat_number: int
    berth_type: str
    compartment: int
    vacant_until_station: StationInfo
    note: str


class CoachVacancy(BaseModel):
    coach: str
    class_type: str
    fully_vacant: list[VacantSeat]
    becomes_vacant: list[BecomesVacantSeat]
    vacant_until: list[VacantUntilSeat]


class VacancySummary(BaseModel):
    total_seats_in_class: int
    fully_vacant: int
    becomes_vacant_midway: int
    vacant_until_midway: int
    occupied: int


class VacancyResponse(BaseModel):
    train_number: str
    train_name: str
    journey_date: date
    from_station: str
    to_station: str
    class_type: str
    summary: VacancySummary
    coaches: list[CoachVacancy]


# --- Service ---


async def _get_train_and_stops(
    db: AsyncSession, train_number: str, from_code: str, to_code: str
) -> tuple[Train, TrainScheduleStop, TrainScheduleStop]:
    """Get train and validate that both stations are on this train's route."""
    result = await db.execute(select(Train).where(Train.number == train_number))
    train = result.scalar_one_or_none()
    if not train:
        raise NotFoundError(f"Train {train_number} not found")

    # Get stop sequences for both stations
    from_result = await db.execute(
        select(TrainScheduleStop).where(
            TrainScheduleStop.train_id == train.id,
            TrainScheduleStop.station_code == from_code.upper(),
        )
    )
    from_stop = from_result.scalar_one_or_none()
    if not from_stop:
        raise BadRequestError(f"Station {from_code} is not on train {train_number}")

    to_result = await db.execute(
        select(TrainScheduleStop).where(
            TrainScheduleStop.train_id == train.id,
            TrainScheduleStop.station_code == to_code.upper(),
        )
    )
    to_stop = to_result.scalar_one_or_none()
    if not to_stop:
        raise BadRequestError(f"Station {to_code} is not on train {train_number}")

    if from_stop.stop_sequence >= to_stop.stop_sequence:
        raise BadRequestError(
            f"{from_code} must come before {to_code} on this train's route"
        )

    return train, from_stop, to_stop


async def _get_stop_info(
    db: AsyncSession, train_id: UUID, stop_seq: int
) -> TrainScheduleStop:
    result = await db.execute(
        select(TrainScheduleStop).where(
            TrainScheduleStop.train_id == train_id,
            TrainScheduleStop.stop_sequence == stop_seq,
        )
    )
    return result.scalar_one()


async def find_vacant_seats(
    db: AsyncSession,
    train_number: str,
    journey_date: date,
    from_code: str,
    to_code: str,
    class_type: str,
    berth_filter: str | None = None,
    group_size: int | None = None,
) -> VacancyResponse:
    train, from_stop, to_stop = await _get_train_and_stops(
        db, train_number, from_code, to_code
    )
    user_from_seq = from_stop.stop_sequence
    user_to_seq = to_stop.stop_sequence

    # Get all seats for this train in the requested class
    coaches_result = await db.execute(
        select(TrainCoach)
        .where(
            TrainCoach.train_id == train.id,
            TrainCoach.class_type == class_type.upper(),
        )
        .order_by(TrainCoach.coach_position)
    )
    coaches = coaches_result.scalars().all()
    if not coaches:
        raise NotFoundError(f"No {class_type} class coaches on train {train_number}")

    coach_ids = [c.id for c in coaches]

    # Get all seats
    seats_query = select(Seat).where(Seat.train_coach_id.in_(coach_ids))
    if berth_filter:
        seats_query = seats_query.where(Seat.berth_type == berth_filter.upper())
    seats_result = await db.execute(seats_query.order_by(Seat.seat_number))
    all_seats = seats_result.scalars().all()

    # Get all bookings that overlap with user's journey segment
    seat_ids = [s.id for s in all_seats]
    bookings_result = await db.execute(
        select(SeatMap).where(
            SeatMap.train_id == train.id,
            SeatMap.journey_date == journey_date,
            SeatMap.seat_id.in_(seat_ids),
            SeatMap.boarding_stop_seq < user_to_seq,  # Overlap condition
            SeatMap.deboarding_stop_seq > user_from_seq,  # Overlap condition
            SeatMap.status.in_(["BOOKED", "RAC"]),
        )
    )
    bookings = bookings_result.scalars().all()

    # Build seat_id → list of bookings map
    seat_bookings: dict[UUID, list[SeatMap]] = {}
    for b in bookings:
        seat_bookings.setdefault(b.seat_id, []).append(b)

    # Build coach_id → coach map
    coach_map = {c.id: c for c in coaches}

    # Classify each seat
    coach_vacancies: dict[UUID, CoachVacancy] = {}
    total_seats = 0
    total_fully_vacant = 0
    total_becomes_vacant = 0
    total_vacant_until = 0
    total_occupied = 0

    for seat in all_seats:
        total_seats += 1
        coach = coach_map[seat.train_coach_id]

        if coach.id not in coach_vacancies:
            coach_vacancies[coach.id] = CoachVacancy(
                coach=coach.coach_label,
                class_type=coach.class_type,
                fully_vacant=[],
                becomes_vacant=[],
                vacant_until=[],
            )

        cv = coach_vacancies[coach.id]
        seat_bkgs = seat_bookings.get(seat.id, [])

        if not seat_bkgs:
            # No overlapping bookings — FULLY VACANT
            cv.fully_vacant.append(
                VacantSeat(
                    seat_number=seat.seat_number,
                    berth_type=seat.berth_type,
                    compartment=seat.compartment_number,
                )
            )
            total_fully_vacant += 1
        else:
            # Check if there's a gap at the start (vacant until someone boards)
            # or a gap at the end (becomes vacant after someone deboards)
            classified = False

            for bkg in seat_bkgs:
                if (
                    bkg.boarding_stop_seq <= user_from_seq
                    and bkg.deboarding_stop_seq >= user_to_seq
                ):
                    # Full overlap — OCCUPIED for entire journey
                    total_occupied += 1
                    classified = True
                    break

            if not classified:
                # Check for partial overlaps
                # Earliest boarding and latest deboarding among all bookings
                earliest_boarding = min(b.boarding_stop_seq for b in seat_bkgs)
                latest_deboarding = max(b.deboarding_stop_seq for b in seat_bkgs)

                if latest_deboarding <= user_to_seq and earliest_boarding <= user_from_seq:
                    # Passenger(s) deboard before our destination — BECOMES VACANT
                    deboard_bkg = max(seat_bkgs, key=lambda b: b.deboarding_stop_seq)
                    stop_info = await _get_stop_info(
                        db, train.id, deboard_bkg.deboarding_stop_seq
                    )
                    cv.becomes_vacant.append(
                        BecomesVacantSeat(
                            seat_number=seat.seat_number,
                            berth_type=seat.berth_type,
                            compartment=seat.compartment_number,
                            vacant_from_station=StationInfo(
                                code=stop_info.station_code,
                                time=str(stop_info.arrival_time) if stop_info.arrival_time else None,
                            ),
                            note=f"Passenger deboarding at {stop_info.station_code}",
                        )
                    )
                    total_becomes_vacant += 1
                elif earliest_boarding > user_from_seq:
                    # Passenger boards after our start — VACANT UNTIL
                    board_bkg = min(seat_bkgs, key=lambda b: b.boarding_stop_seq)
                    stop_info = await _get_stop_info(
                        db, train.id, board_bkg.boarding_stop_seq
                    )
                    cv.vacant_until.append(
                        VacantUntilSeat(
                            seat_number=seat.seat_number,
                            berth_type=seat.berth_type,
                            compartment=seat.compartment_number,
                            vacant_until_station=StationInfo(
                                code=stop_info.station_code,
                                time=str(stop_info.departure_time) if stop_info.departure_time else None,
                            ),
                            note=f"Passenger boarding at {stop_info.station_code}",
                        )
                    )
                    total_vacant_until += 1
                else:
                    total_occupied += 1

    return VacancyResponse(
        train_number=train.number,
        train_name=train.name,
        journey_date=journey_date,
        from_station=from_code.upper(),
        to_station=to_code.upper(),
        class_type=class_type.upper(),
        summary=VacancySummary(
            total_seats_in_class=total_seats,
            fully_vacant=total_fully_vacant,
            becomes_vacant_midway=total_becomes_vacant,
            vacant_until_midway=total_vacant_until,
            occupied=total_occupied,
        ),
        coaches=[cv for cv in coach_vacancies.values()],
    )


# --- Router ---

router = APIRouter(prefix="/vacancy", tags=["Vacancy"])


@router.get("/find", response_model=VacancyResponse)
async def find_vacancy(
    train_number: str = Query(..., description="Train number"),
    date: date = Query(..., description="Journey date"),
    from_station: str = Query(..., alias="from", description="Boarding station code"),
    to_station: str = Query(..., alias="to", description="Deboarding station code"),
    class_type: str = Query("SL", alias="class", description="Class: SL, 3A, 2A, 1A, CC, 2S"),
    berth: str | None = Query(None, description="Filter: LOWER, UPPER, MIDDLE, SIDE_LOWER, SIDE_UPPER"),
    group_size: int | None = Query(None, ge=2, le=8, description="Find adjacent vacant seats for a group"),
    db: AsyncSession = Depends(get_db),
):
    return await find_vacant_seats(
        db, train_number, date, from_station, to_station, class_type, berth, group_size
    )


@router.get("/summary")
async def vacancy_summary(
    train_number: str = Query(...),
    date: date = Query(...),
    from_station: str = Query(..., alias="from"),
    to_station: str = Query(..., alias="to"),
    class_type: str = Query("SL", alias="class"),
    db: AsyncSession = Depends(get_db),
):
    result = await find_vacant_seats(
        db, train_number, date, from_station, to_station, class_type
    )
    return result.summary

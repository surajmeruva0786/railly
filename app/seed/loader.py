import json
import random
from datetime import date, time as dt_time, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SEED_DIR = Path(__file__).parent

# Berth layouts per class
BERTH_LAYOUTS = {
    "SL": {
        "berths_per_compartment": 8,
        "compartments": 9,
        "pattern": ["LOWER", "MIDDLE", "UPPER", "LOWER", "MIDDLE", "UPPER", "SIDE_LOWER", "SIDE_UPPER"],
        "prefix": "S",
        "coaches_count": 8,
    },
    "3A": {
        "berths_per_compartment": 8,
        "compartments": 9,
        "pattern": ["LOWER", "MIDDLE", "UPPER", "LOWER", "MIDDLE", "UPPER", "SIDE_LOWER", "SIDE_UPPER"],
        "prefix": "B",
        "coaches_count": 3,
    },
    "2A": {
        "berths_per_compartment": 6,
        "compartments": 8,
        "pattern": ["LOWER", "UPPER", "LOWER", "UPPER", "SIDE_LOWER", "SIDE_UPPER"],
        "prefix": "A",
        "coaches_count": 2,
    },
}


async def seed_stations(db: AsyncSession):
    from app.models.station import Station

    result = await db.execute(select(Station).limit(1))
    if result.scalar_one_or_none():
        print("Stations already seeded, skipping.")
        return

    data = json.loads((SEED_DIR / "stations.json").read_text())
    for s in data:
        db.add(Station(**s))
    await db.commit()
    print(f"Seeded {len(data)} stations.")


async def seed_trains(db: AsyncSession):
    from app.models.train import Train, TrainScheduleStop

    result = await db.execute(select(Train).limit(1))
    if result.scalar_one_or_none():
        print("Trains already seeded, skipping.")
        return

    data = json.loads((SEED_DIR / "trains.json").read_text())
    for t in data:
        schedule_data = t.pop("schedule")
        train = Train(**t)
        db.add(train)
        await db.flush()

        for stop in schedule_data:
            for field in ("arrival_time", "departure_time"):
                if stop[field]:
                    h, m = map(int, stop[field].split(":"))
                    stop[field] = dt_time(h, m)
            db.add(TrainScheduleStop(train_id=train.id, **stop))

    await db.commit()
    print(f"Seeded {len(data)} trains with schedules.")


async def seed_coaches_and_seats(db: AsyncSession):
    from app.models.coach import Seat, TrainCoach
    from app.models.train import Train

    result = await db.execute(select(TrainCoach).limit(1))
    if result.scalar_one_or_none():
        print("Coaches already seeded, skipping.")
        return

    trains_result = await db.execute(select(Train))
    trains = trains_result.scalars().all()

    total_coaches = 0
    total_seats = 0

    for train in trains:
        position = 1
        for class_type, layout in BERTH_LAYOUTS.items():
            for coach_num in range(1, layout["coaches_count"] + 1):
                label = f"{layout['prefix']}{coach_num}"
                total_berths = layout["berths_per_compartment"] * layout["compartments"]

                coach = TrainCoach(
                    train_id=train.id,
                    coach_label=label,
                    class_type=class_type,
                    total_berths=total_berths,
                    coach_position=position,
                )
                db.add(coach)
                await db.flush()
                total_coaches += 1
                position += 1

                seat_num = 1
                for comp in range(1, layout["compartments"] + 1):
                    for berth_type in layout["pattern"]:
                        db.add(
                            Seat(
                                train_coach_id=coach.id,
                                seat_number=seat_num,
                                berth_type=berth_type,
                                compartment_number=comp,
                            )
                        )
                        seat_num += 1
                        total_seats += 1

    await db.commit()
    print(f"Seeded {total_coaches} coaches with {total_seats} seats.")


async def seed_mock_bookings(db: AsyncSession):
    """Generate realistic mock seat_map entries for train 18519 (VSKP→LTT)
    to demonstrate the vacancy finder. Creates bookings with varied
    boarding/deboarding stations to show all vacancy types.
    """
    from app.models.coach import Seat, TrainCoach
    from app.models.seat_map import SeatMap
    from app.models.train import Train

    result = await db.execute(select(SeatMap).limit(1))
    if result.scalar_one_or_none():
        print("Mock bookings already seeded, skipping.")
        return

    # Get train 18519
    train_result = await db.execute(select(Train).where(Train.number == "18519"))
    train = train_result.scalar_one_or_none()
    if not train:
        print("Train 18519 not found, skipping mock bookings.")
        return

    # Get SL coaches for this train
    coaches_result = await db.execute(
        select(TrainCoach)
        .where(TrainCoach.train_id == train.id, TrainCoach.class_type == "SL")
        .order_by(TrainCoach.coach_position)
    )
    coaches = coaches_result.scalars().all()

    # Generate bookings for multiple dates
    today = date.today()
    dates_to_seed = [today + timedelta(days=i) for i in range(1, 4)]

    # Sample booking patterns — varied segments to showcase vacancy finder
    booking_patterns = [
        # Full journey passengers (VSKP to LTT)
        {"from_seq": 1, "to_seq": 14, "from_code": "VSKP", "to_code": "LTT"},
        # Short-distance passengers (will vacate seats mid-journey)
        {"from_seq": 1, "to_seq": 5, "from_code": "VSKP", "to_code": "BZA"},
        {"from_seq": 1, "to_seq": 4, "from_code": "VSKP", "to_code": "RJY"},
        {"from_seq": 1, "to_seq": 7, "from_code": "VSKP", "to_code": "BPQ"},
        # Mid-board passengers (board after VSKP)
        {"from_seq": 4, "to_seq": 11, "from_code": "RJY", "to_code": "R"},
        {"from_seq": 5, "to_seq": 14, "from_code": "BZA", "to_code": "LTT"},
        {"from_seq": 7, "to_seq": 14, "from_code": "BPQ", "to_code": "LTT"},
        {"from_seq": 9, "to_seq": 14, "from_code": "NGP", "to_code": "LTT"},
        # Short mid-journey
        {"from_seq": 5, "to_seq": 9, "from_code": "BZA", "to_code": "NGP"},
        {"from_seq": 7, "to_seq": 11, "from_code": "BPQ", "to_code": "R"},
        {"from_seq": 4, "to_seq": 7, "from_code": "RJY", "to_code": "BPQ"},
    ]

    names = [
        "Rajesh Kumar", "Priya Sharma", "Arun Singh", "Deepa Patel",
        "Vikram Reddy", "Meera Nair", "Suresh Yadav", "Anita Das",
        "Ramesh Gupta", "Sita Devi", "Mohan Rao", "Kavita Joshi",
        "Amit Verma", "Pooja Mishra", "Kiran Bhat", "Lakshmi Iyer",
    ]

    total_bookings = 0
    random.seed(42)  # Reproducible

    for journey_date in dates_to_seed:
        for coach in coaches:
            seats_result = await db.execute(
                select(Seat)
                .where(Seat.train_coach_id == coach.id)
                .order_by(Seat.seat_number)
            )
            seats = seats_result.scalars().all()

            # Book ~60% of seats with varied patterns
            num_to_book = int(len(seats) * 0.6)
            seats_to_book = random.sample(seats, min(num_to_book, len(seats)))

            for seat in seats_to_book:
                pattern = random.choice(booking_patterns)
                pnr = f"{random.randint(1000000000, 9999999999)}"
                name = random.choice(names)

                db.add(
                    SeatMap(
                        seat_id=seat.id,
                        train_id=train.id,
                        journey_date=journey_date,
                        boarding_stop_seq=pattern["from_seq"],
                        deboarding_stop_seq=pattern["to_seq"],
                        boarding_station_code=pattern["from_code"],
                        deboarding_station_code=pattern["to_code"],
                        status="BOOKED",
                        passenger_name=name,
                        pnr_number=pnr,
                        coach_label=coach.coach_label,
                        seat_number=seat.seat_number,
                        berth_type=seat.berth_type,
                    )
                )
                total_bookings += 1

    await db.commit()
    print(f"Seeded {total_bookings} mock bookings across {len(dates_to_seed)} dates.")


async def seed_all(db: AsyncSession):
    await seed_stations(db)
    await seed_trains(db)
    await seed_coaches_and_seats(db)
    await seed_mock_bookings(db)

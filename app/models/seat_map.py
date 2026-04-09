import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SeatMap(Base):
    """One row per booked seat per journey date. Populated from chart data.
    This is THE core table powering the vacancy finder.
    """

    __tablename__ = "seat_map"
    __table_args__ = (
        Index(
            "ix_seat_map_vacancy_lookup",
            "train_id",
            "journey_date",
            "boarding_stop_seq",
            "deboarding_stop_seq",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seats.id", ondelete="CASCADE"), index=True
    )
    train_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trains.id", ondelete="CASCADE")
    )
    journey_date: Mapped[date] = mapped_column(Date)
    boarding_stop_seq: Mapped[int] = mapped_column(Integer)
    deboarding_stop_seq: Mapped[int] = mapped_column(Integer)
    boarding_station_code: Mapped[str] = mapped_column(String(10))
    deboarding_station_code: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(15))  # BOOKED, RAC
    passenger_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    pnr_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Denormalized for fast queries
    coach_label: Mapped[str] = mapped_column(String(10))
    seat_number: Mapped[int] = mapped_column(Integer)
    berth_type: Mapped[str] = mapped_column(String(12))

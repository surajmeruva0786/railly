import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReservationChart(Base):
    __tablename__ = "reservation_charts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    train_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trains.id", ondelete="CASCADE"), index=True
    )
    journey_date: Mapped[date] = mapped_column(Date)
    chart_sequence: Mapped[int] = mapped_column(Integer, default=1)  # 1st or 2nd chart
    status: Mapped[str] = mapped_column(String(15))  # PENDING, PREPARED, FINAL
    prepared_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    entries: Mapped[list["ChartEntry"]] = relationship(back_populates="chart")


class ChartEntry(Base):
    __tablename__ = "chart_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reservation_charts.id", ondelete="CASCADE"), index=True
    )
    coach_label: Mapped[str] = mapped_column(String(10))
    seat_number: Mapped[int] = mapped_column(Integer)
    berth_type: Mapped[str] = mapped_column(String(12))
    passenger_name: Mapped[str] = mapped_column(String(150))
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(1))
    from_station_code: Mapped[str] = mapped_column(String(10))
    to_station_code: Mapped[str] = mapped_column(String(10))
    booking_status: Mapped[str] = mapped_column(String(20))  # CNF, RAC
    pnr_number: Mapped[str] = mapped_column(String(10))

    chart: Mapped["ReservationChart"] = relationship(back_populates="entries")

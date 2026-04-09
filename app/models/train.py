import uuid
from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Train(Base):
    __tablename__ = "trains"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    train_type: Mapped[str] = mapped_column(String(20))  # EXPRESS, SUPERFAST, RAJDHANI, etc.
    source_station_code: Mapped[str] = mapped_column(
        ForeignKey("stations.code"), index=True
    )
    destination_station_code: Mapped[str] = mapped_column(
        ForeignKey("stations.code"), index=True
    )
    runs_on_days: Mapped[str] = mapped_column(String(7))  # "1111111" = daily
    total_distance_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_pantry: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    schedule: Mapped[list["TrainScheduleStop"]] = relationship(
        back_populates="train", order_by="TrainScheduleStop.stop_sequence"
    )


class TrainScheduleStop(Base):
    __tablename__ = "train_schedule_stops"
    __table_args__ = (
        UniqueConstraint("train_id", "stop_sequence", name="uq_train_stop_seq"),
        UniqueConstraint("train_id", "station_code", name="uq_train_station"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    train_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trains.id", ondelete="CASCADE"), index=True
    )
    station_code: Mapped[str] = mapped_column(ForeignKey("stations.code"))
    stop_sequence: Mapped[int] = mapped_column(Integer)
    arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)  # null for source
    departure_time: Mapped[time | None] = mapped_column(Time, nullable=True)  # null for dest
    halt_minutes: Mapped[int] = mapped_column(Integer, default=0)
    distance_from_source_km: Mapped[int] = mapped_column(Integer, default=0)
    day_offset: Mapped[int] = mapped_column(Integer, default=0)  # 0=day1, 1=day2

    train: Mapped["Train"] = relationship(back_populates="schedule")

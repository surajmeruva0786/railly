import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TrainCoach(Base):
    __tablename__ = "train_coaches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    train_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trains.id", ondelete="CASCADE"), index=True
    )
    coach_label: Mapped[str] = mapped_column(String(10))  # e.g. "S1", "B1", "A1"
    class_type: Mapped[str] = mapped_column(String(5))  # SL, 3A, 2A, 1A, CC, 2S
    total_berths: Mapped[int] = mapped_column(Integer)
    coach_position: Mapped[int] = mapped_column(Integer)

    seats: Mapped[list["Seat"]] = relationship(back_populates="coach")


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("train_coach_id", "seat_number", name="uq_coach_seat"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    train_coach_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("train_coaches.id", ondelete="CASCADE"), index=True
    )
    seat_number: Mapped[int] = mapped_column(Integer)
    berth_type: Mapped[str] = mapped_column(String(12))  # LOWER, MIDDLE, UPPER, SIDE_LOWER, SIDE_UPPER
    compartment_number: Mapped[int] = mapped_column(Integer)
    is_accessible: Mapped[bool] = mapped_column(Boolean, default=False)

    coach: Mapped["TrainCoach"] = relationship(back_populates="seats")

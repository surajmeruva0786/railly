from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Station(Base):
    __tablename__ = "stations"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    state: Mapped[str] = mapped_column(String(50))
    zone: Mapped[str] = mapped_column(String(10))
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    is_junction: Mapped[bool] = mapped_column(Boolean, default=False)

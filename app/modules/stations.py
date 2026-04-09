from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import NotFoundError
from app.models.station import Station

# --- Schemas ---


class StationResponse(BaseModel):
    code: str
    name: str
    city: str
    state: str
    zone: str
    is_junction: bool

    model_config = {"from_attributes": True}


# --- Service ---


async def search_stations(
    db: AsyncSession, query: str, limit: int = 10
) -> list[Station]:
    q = query.upper()
    stmt = (
        select(Station)
        .where(
            or_(
                Station.code.ilike(f"%{q}%"),
                Station.name.ilike(f"%{q}%"),
                Station.city.ilike(f"%{q}%"),
            )
        )
        .order_by(
            # Exact code match first, then by name
            Station.code == q,
            Station.name,
        )
        .limit(limit)
    )
    # Sort: exact code match comes first (desc because True > False)
    stmt = (
        select(Station)
        .where(
            or_(
                Station.code.ilike(f"%{q}%"),
                Station.name.ilike(f"%{q}%"),
                Station.city.ilike(f"%{q}%"),
            )
        )
        .order_by((Station.code == q).desc(), Station.name)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_station(db: AsyncSession, code: str) -> Station:
    result = await db.execute(
        select(Station).where(Station.code == code.upper())
    )
    station = result.scalar_one_or_none()
    if not station:
        raise NotFoundError(f"Station '{code}' not found")
    return station


# --- Router ---

router = APIRouter(prefix="/stations", tags=["Stations"])


@router.get("/", response_model=list[StationResponse])
async def list_stations(
    q: str = Query(..., min_length=1, description="Search by code, name, or city"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    return await search_stations(db, q, limit)


@router.get("/{code}", response_model=StationResponse)
async def get_station_detail(code: str, db: AsyncSession = Depends(get_db)):
    return await get_station(db, code)

"""Seed the database with initial data. Run with: python -m scripts.seed_db"""

import asyncio

from app.database import async_session


async def main():
    from app.seed.loader import seed_all

    async with async_session() as db:
        await seed_all(db)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())

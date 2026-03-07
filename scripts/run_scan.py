import asyncio

from app.db import SessionLocal, init_db
from app.pipeline import JobPipeline


async def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        result = await JobPipeline().run(db)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())

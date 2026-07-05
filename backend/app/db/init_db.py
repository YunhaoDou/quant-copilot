"""Create all tables from ORM metadata. MVP shortcut in place of Alembic migrations."""
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403  (registers models on Base.metadata)


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

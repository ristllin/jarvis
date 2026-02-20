import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

data_dir = os.environ.get("DATA_DIR", "/data")
db_path = os.path.join(data_dir, "jarvis.db")
os.makedirs(data_dir, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight column migrations for SQLite
        await _migrate_columns(conn)


async def _migrate_columns(conn):
    """Add missing columns to existing tables (SQLite doesn't support ALTER TABLE ADD IF NOT EXISTS)."""
    import sqlalchemy as sa

    migrations = [
        ("jarvis_state", "short_term_memories", "TEXT DEFAULT '[]'"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(sa.text(f"SELECT {column} FROM {table} LIMIT 1"))
        except Exception:
            try:
                await conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            except Exception:
                pass

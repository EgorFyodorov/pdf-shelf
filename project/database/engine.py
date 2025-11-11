import logging
from typing import Tuple
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from project.schemas.config_schemas import PostgresSection

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker | None = None


def build_connection_url(postgres: PostgresSection) -> str:
    password = quote_plus(postgres.password or "")
    return (
        f"postgresql+asyncpg://{postgres.user}:{password}"
        f"@{postgres.host}:{postgres.port}/{postgres.database}"
    )


def init_engine(config: PostgresSection) -> Tuple[AsyncEngine, async_sessionmaker]:
    global _engine, _session_maker
    if _engine and _session_maker:
        return _engine, _session_maker

    dsn = build_connection_url(config)
    logger.info(
        "Initializing SQLAlchemy engine for postgres://%s@%s:%s/%s",
        config.user,
        config.host,
        config.port,
        config.database,
    )
    _engine = create_async_engine(dsn, pool_pre_ping=True, future=True)
    _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine, _session_maker


async def verify_connection(engine: AsyncEngine):
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    logger.info("Postgres connection verified.")


def get_sessionmaker() -> async_sessionmaker:
    if not _session_maker:
        raise RuntimeError(
            "Database sessionmaker is not initialized. Call init_engine first."
        )
    return _session_maker

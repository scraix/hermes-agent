"""Database session management for Memory Graph.

Provides async SQLAlchemy session factory using PostgreSQL.
Shares the same database as Hindsight (default: hindsight DB).
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from . import models as Base  # noqa: F401 — ensure models are loaded

logger = logging.getLogger(__name__)

DEFAULT_DB_URL = "postgresql+asyncpg://postgres:20090603Sg%2B@127.0.0.1/hindsight"

_engine = None
_session_factory = None


def get_db_url() -> str:
    """Get database URL from environment or default."""
    return os.environ.get("MEMORY_GRAPH_DB_URL", DEFAULT_DB_URL)


async def init_db(db_url: str = None) -> None:
    """Initialize the async engine and create tables if needed."""
    global _engine, _session_factory
    url = db_url or get_db_url()
    from sqlalchemy.pool import NullPool
    _engine = create_async_engine(url, echo=False, poolclass=NullPool)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # Create tables
    async with _engine.begin() as conn:
        from .models import Base as ModelBase
        await conn.run_sync(ModelBase.metadata.create_all)

    # Ensure root node exists
    async with _session_factory() as session:
        from .models import ROOT_NODE_UUID, Node
        from sqlalchemy import select
        result = await session.execute(select(Node).where(Node.uuid == ROOT_NODE_UUID))
        if result.scalar_one_or_none() is None:
            session.add(Node(uuid=ROOT_NODE_UUID))
            await session.commit()
            logger.info("Created root node %s", ROOT_NODE_UUID)

    logger.info("Memory Graph DB initialized: %s", url.split("@")[-1] if "@" in url else url)


async def close_db() -> None:
    """Dispose the engine."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def get_session() -> AsyncSession:
    """Get an auto-commit async session. Use as async context manager."""
    if _session_factory is None:
        raise RuntimeError("Memory Graph DB not initialized. Call init_db() first.")
    return _session_factory()


def get_session_no_commit() -> AsyncSession:
    """Get a session that does NOT auto-commit on __aexit__."""
    if _session_factory is None:
        raise RuntimeError("Memory Graph DB not initialized. Call init_db() first.")
    return _session_factory()


def get_engine():
    """Get the underlying async engine."""
    if _engine is None:
        raise RuntimeError("Memory Graph DB not initialized. Call init_db() first.")
    return _engine

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SessionFactory = async_sessionmaker[AsyncSession]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: SessionFactory | None = request.app.state.session_factory
    if factory is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database not configured")
    async with factory() as session:
        yield session

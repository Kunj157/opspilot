"""A database outage is unavailability, not a server bug: 503 with Retry-After.

Connection failures (refused, reset, pool timeout) surface as SQLAlchemy
OperationalError, InterfaceError, or pool TimeoutError. They become a 503 so
clients and load balancers retry instead of reporting a 500, and the error
budget alerts can tell an outage from a defect. Details stay in the log.
"""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

logger = structlog.get_logger()

RETRY_AFTER_SECONDS = "5"


async def database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("database unavailable", error_type=type(exc).__name__, path=request.url.path)
    return JSONResponse(
        {"detail": "Database unavailable, retry shortly"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )


def install(app: FastAPI) -> None:
    for error in (OperationalError, InterfaceError, PoolTimeoutError):
        app.add_exception_handler(error, database_unavailable)

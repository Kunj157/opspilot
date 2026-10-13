"""Run the API in a real uvicorn server (needed for streaming responses)."""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn

from opspilot_api.auth.dependencies import get_token_verifier
from opspilot_api.auth.tokens import TokenVerifier
from opspilot_api.config import Settings
from opspilot_api.main import create_app
from tests.support.tokens import AUDIENCE, ISSUER, TokenFactory


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@asynccontextmanager
async def live_server(
    database_url: str, factory: TokenFactory, **settings: Any
) -> AsyncIterator[str]:
    async def resolve(_token: str) -> Any:
        return factory.public_key

    app = create_app(
        Settings(
            app_env="test",
            database_url=database_url,
            redis_url="redis://unused:6379/0",
            jwt_issuer=ISSUER,
            jwt_audience=AUDIENCE,
            **settings,
        )
    )
    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_resolver=resolve)
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    task = asyncio.create_task(server.serve())
    async with asyncio.timeout(10):
        while not server.started:  # noqa: ASYNC110 - uvicorn exposes no event to await
            await asyncio.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task

"""A worker process for the kill test: runs one investigation with a slow scripted model.

    python worker_child.py <database-url>

Every model answer takes MODEL_DELAY seconds, so the parent can SIGKILL the
process in the middle of the workflow.
"""

import asyncio
import os
import sys
import time
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.test_investigation_runner import happy_model, runner


async def main(database_url: str) -> None:
    delay = float(os.environ.get("MODEL_DELAY", "1.0"))
    answer = happy_model()

    def slow(schema: type[BaseModel], prompt: str) -> dict[str, Any]:
        time.sleep(delay)  # blocks the loop on purpose: a model that takes its time
        return answer(schema, prompt)

    engine = create_async_engine(database_url)
    await runner(async_sessionmaker(engine, expire_on_commit=False), slow).run_once()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))

"""Register a trained model from its evaluation report.

uv run python -m opspilot_api.ml register ../../ml/evaluation/report-v1.json [--promote]
"""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opspilot_api.config import get_settings
from opspilot_api.ml.registry import promote, read_report, register


async def _register(report: Path, promote_it: bool) -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required")
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        model = await register(session, *read_report(report))
        if promote_it:
            await promote(session, model)
        await session.commit()
        print(f"registered {model.name}:{model.version} ({model.status}) from {report}")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m opspilot_api.ml")
    commands = parser.add_subparsers(dest="command", required=True)
    reg = commands.add_parser("register")
    reg.add_argument("report", type=Path)
    reg.add_argument("--promote", action="store_true", help="run it in shadow mode right away")
    args = parser.parse_args()
    asyncio.run(_register(args.report, args.promote))


if __name__ == "__main__":
    main()

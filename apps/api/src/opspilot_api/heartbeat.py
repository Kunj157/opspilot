"""A heartbeat file for the worker's readiness probe.

The worker has no HTTP API, so it touches a file whenever its database is
reachable; the probe checks that the file is recent:

    python -m opspilot_api.heartbeat /tmp/worker-heartbeat 60   # exit 0 if fresh

Kept free of heavy imports so the probe starts fast.
"""

import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path


def beat(path: Path) -> None:
    path.touch()


def is_fresh(path: Path, max_age: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= max_age
    except FileNotFoundError:
        return False


async def beat_if_healthy(path: Path, check: Callable[[], Awaitable[None]]) -> None:
    """Touch the file only after the check passed; a failing check raises."""
    await check()
    beat(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m opspilot_api.heartbeat <file> <max-age-seconds>", file=sys.stderr)
        return 2
    return 0 if is_fresh(Path(args[0]), float(args[1])) else 1


if __name__ == "__main__":
    raise SystemExit(main())

import os
import time
from pathlib import Path

import pytest

from opspilot_api import heartbeat


def test_missing_file_is_not_fresh(tmp_path: Path) -> None:
    assert not heartbeat.is_fresh(tmp_path / "beat", max_age=30)


def test_recent_beat_is_fresh(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    heartbeat.beat(path)
    assert heartbeat.is_fresh(path, max_age=30)


def test_old_beat_is_stale(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    heartbeat.beat(path)
    old = time.time() - 120
    os.utime(path, (old, old))
    assert not heartbeat.is_fresh(path, max_age=30)


def test_cli_exit_code_follows_freshness(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    assert heartbeat.main([str(path), "30"]) == 1
    heartbeat.beat(path)
    assert heartbeat.main([str(path), "30"]) == 0


async def test_loop_beats_only_while_the_check_passes(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    healthy = True

    async def check() -> None:
        if not healthy:
            raise ConnectionError("database down")

    await heartbeat.beat_if_healthy(path, check)
    assert heartbeat.is_fresh(path, max_age=30)

    old = time.time() - 120
    os.utime(path, (old, old))
    healthy = False
    with pytest.raises(ConnectionError):
        await heartbeat.beat_if_healthy(path, check)
    assert not heartbeat.is_fresh(path, max_age=30)

"""Event tooling.

    uv run python -m opspilot_api.events replay --topic incident.created.v1 \\
        [--from-dlq] [--since 2026-10-14T02:00:00+00:00]
"""

import argparse
import asyncio
from datetime import datetime

from opspilot_api.config import get_settings
from opspilot_api.events.envelope import ALL_TOPICS
from opspilot_api.events.producer import KafkaProducer
from opspilot_api.events.replay import replay


async def _replay(topic: str, from_dlq: bool, since: datetime | None) -> None:
    servers = get_settings().kafka_bootstrap_servers
    if not servers:
        raise SystemExit("KAFKA_BOOTSTRAP_SERVERS is required")
    producer = KafkaProducer(servers)
    try:
        count = await replay(servers, producer, topic, from_dlq=from_dlq, since=since)
    finally:
        await producer.aclose()
    print(f"republished {count} events to {topic}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m opspilot_api.events")
    commands = parser.add_subparsers(dest="command", required=True)
    rep = commands.add_parser("replay", help="republish a topic or its dead-letter topic")
    rep.add_argument("--topic", required=True, choices=ALL_TOPICS)
    rep.add_argument("--from-dlq", action="store_true")
    rep.add_argument("--since", type=datetime.fromisoformat)
    args = parser.parse_args()
    asyncio.run(_replay(args.topic, args.from_dlq, args.since))


if __name__ == "__main__":
    main()

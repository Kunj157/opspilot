"""Replay: republish the events of a topic, or the parked ones of its dead-letter topic.

Consumers are idempotent by event ID, so replaying a topic does nothing for
events already handled and processes only the ones that were not (for
example, parked on the dead-letter topic before a fix).
"""

import uuid
from datetime import datetime

from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient

from opspilot_api.events.envelope import dead_letter
from opspilot_api.events.producer import Producer


async def _partitions(bootstrap_servers: str, topic: str) -> list[int]:
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        described = await admin.describe_topics([topic])
    finally:
        await admin.close()
    return sorted(
        p["partition"]
        for t in described
        if t.get("topic") == topic and not t.get("error_code")
        for p in t.get("partitions", [])
    )


async def replay(
    bootstrap_servers: str,
    producer: Producer,
    topic: str,
    *,
    from_dlq: bool = False,
    since: datetime | None = None,
) -> int:
    """Republish every message of `topic` (or `topic.dlq`) to `topic`; returns the count."""
    source = dead_letter(topic) if from_dlq else topic
    # A throwaway group that never commits: replay never moves real consumers.
    consumer = AIOKafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id=f"replay-{uuid.uuid4().hex[:8]}",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    count = 0
    try:
        partitions = [
            TopicPartition(source, p) for p in await _partitions(bootstrap_servers, source)
        ]
        if not partitions:
            return 0
        consumer.assign(partitions)
        ends = await consumer.end_offsets(partitions)
        if since is not None:
            starts = await consumer.offsets_for_times(
                {tp: int(since.timestamp() * 1000) for tp in partitions}
            )
            for tp in partitions:
                found = starts.get(tp)
                consumer.seek(tp, found.offset if found else ends[tp])
        else:
            await consumer.seek_to_beginning(*partitions)
        remaining = {tp for tp in partitions if await consumer.position(tp) < ends[tp]}
        while remaining:
            batches = await consumer.getmany(*remaining, timeout_ms=1000)
            for tp, records in batches.items():
                for record in records:
                    if record.offset >= ends[tp]:
                        continue
                    headers = [(k, v) for k, v in record.headers if k not in {"error", "consumer"}]
                    await producer.send(topic, record.key or b"", record.value or b"", headers)
                    count += 1
            remaining = {tp for tp in remaining if await consumer.position(tp) < ends[tp]}
    finally:
        await consumer.stop()
    return count

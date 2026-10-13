"""Opaque keyset page tokens for lists ordered by (timestamp, id) descending."""

import base64
import binascii
import uuid
from datetime import datetime

from fastapi import HTTPException, status


def encode_page_token(timestamp: datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{timestamp.isoformat()}|{row_id}".encode()).decode()


def decode_page_token(token: str) -> tuple[datetime, uuid.UUID]:
    try:
        timestamp, row_id = base64.urlsafe_b64decode(token.encode()).decode().split("|")
        return datetime.fromisoformat(timestamp), uuid.UUID(row_id)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid page token") from exc

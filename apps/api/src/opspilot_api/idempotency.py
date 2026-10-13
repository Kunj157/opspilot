"""Idempotency-Key support for create requests (DEVELOPMENT_PLAN.md §14).

The key row is inserted in the same transaction as the resource it creates:
- a concurrent duplicate blocks on the primary key until the first request
  commits, then replays its stored response, so only one record is created;
- if the request fails and rolls back, the key disappears with it and can be
  retried.
"""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from opspilot_api.auth.principal import Principal
from opspilot_api.db.models import IdempotencyKey

TTL = timedelta(hours=24)
_VALID_KEY = re.compile(r"^[\x21-\x7e]{1,255}$")
REPLAYED_HEADER = "Idempotency-Replayed"


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["header", "Idempotency-Key"], "msg": message, "type": "value_error"}],
    )


def idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    if key is None:
        return None
    if not _VALID_KEY.fullmatch(key):
        raise _invalid("must be 1-255 visible ASCII characters")
    return key


class Idempotency:
    """Per-request helper: `replay()` before doing work, `remember()` before commit."""

    def __init__(
        self, session: AsyncSession, principal: Principal, request: Request, key: str | None
    ) -> None:
        self._session = session
        self._principal = principal
        self._request = request
        self._key = key

    async def replay(self, body: BaseModel) -> JSONResponse | None:
        if self._key is None:
            return None
        org = self._principal.organization_id
        fingerprint = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        now = datetime.now(UTC)
        await self._session.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.organization_id == org,
                IdempotencyKey.key == self._key,
                IdempotencyKey.expires_at <= now,
            )
        )
        inserted = await self._session.execute(
            insert(IdempotencyKey)
            .values(
                organization_id=org,
                key=self._key,
                method=self._request.method,
                path=self._request.url.path,
                request_hash=fingerprint,
                expires_at=now + TTL,
            )
            .on_conflict_do_nothing()
            .returning(IdempotencyKey.key)
        )
        if inserted.scalar_one_or_none() is not None:
            return None  # first time: the caller does the work

        stored = (
            await self._session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.organization_id == org, IdempotencyKey.key == self._key
                )
            )
        ).scalar_one()
        same_request = (stored.method, stored.path, stored.request_hash) == (
            self._request.method,
            self._request.url.path,
            fingerprint,
        )
        if not same_request:
            raise _invalid("was already used for a different request")
        if stored.response_status is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A request with this key is in progress")
        return JSONResponse(
            stored.response_body,
            status_code=stored.response_status,
            headers={REPLAYED_HEADER: "true"},
        )

    async def remember(self, status_code: int, body: dict[str, Any]) -> None:
        if self._key is None:
            return
        stored = await self._session.get(
            IdempotencyKey, (self._principal.organization_id, self._key)
        )
        if stored is not None:
            stored.response_status = status_code
            stored.response_body = body

import base64
import json

import pytest
import structlog

from opspilot_api.redaction import REDACTED, redact


def _fake_jwt() -> str:
    """A token-shaped string built at runtime so no credential-like literal is committed."""

    def part(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    return ".".join([part(b'{"alg":"RS256"}'), part(b'{"sub":"1"}'), part(b"signature")])


FAKE_JWT = _fake_jwt()


def test_redacts_sensitive_keys_recursively() -> None:
    data = {
        "username": "cleo",
        "password": "hunter2",
        "headers": {"Authorization": "Bearer abc", "Cookie": "s=1", "Accept": "json"},
        "nested": [{"client_secret": "x", "api_key": "y", "note": "keep"}],
        "refresh_token": "r",
    }

    assert redact(data) == {
        "username": "cleo",
        "password": REDACTED,
        "headers": {"Authorization": REDACTED, "Cookie": REDACTED, "Accept": "json"},
        "nested": [{"client_secret": REDACTED, "api_key": REDACTED, "note": "keep"}],
        "refresh_token": REDACTED,
    }


@pytest.mark.parametrize(
    "text",
    [
        f"Authorization: Bearer {FAKE_JWT}",
        f"token={FAKE_JWT} in the url",
        "bearer abc.def-ghi_jkl",
    ],
)
def test_masks_tokens_inside_strings(text: str) -> None:
    masked = redact(text)

    assert "eyJ" not in masked
    assert "abc.def" not in masked
    assert REDACTED in masked


def test_leaves_ordinary_values_alone() -> None:
    assert redact({"count": 3, "ok": True, "name": None, "msg": "hello"}) == {
        "count": 3,
        "ok": True,
        "name": None,
        "msg": "hello",
    }


def test_log_output_never_contains_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    from opspilot_api.config import Settings
    from opspilot_api.logging import configure_logging

    configure_logging(Settings(app_env="test"))
    structlog.get_logger().info(
        "outgoing call",
        headers={"authorization": f"Bearer {FAKE_JWT}"},
        password="hunter2",
        detail=f"retrying with Bearer {FAKE_JWT}",
    )

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "hunter2" not in json.dumps(line)
    assert "eyJ" not in json.dumps(line)
    assert line["headers"]["authorization"] == REDACTED

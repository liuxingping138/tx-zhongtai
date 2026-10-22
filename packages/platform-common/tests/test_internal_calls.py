from __future__ import annotations

import pytest
from starlette.requests import Request

from platform_common.errors import InternalCallerRejectedError
from platform_common.internal_calls import internal_headers, verify_internal_caller

SECRETS = {"ai-service": "s3cret"}


def _request(headers: dict[str, str]) -> Request:
    raw = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    return Request({"type": "http", "headers": raw})


def test_known_caller_with_matching_secret_is_accepted() -> None:
    assert verify_internal_caller(_request(internal_headers("ai-service", "s3cret")), SECRETS) == "ai-service"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        internal_headers("ai-service", "wrong!"),
        internal_headers("ai-service", ""),
        internal_headers("policy-service", "s3cret"),
    ],
)
def test_unknown_caller_or_wrong_secret_is_rejected(headers: dict[str, str]) -> None:
    with pytest.raises(InternalCallerRejectedError):
        verify_internal_caller(_request(headers), SECRETS)


def test_nothing_is_accepted_when_no_caller_is_configured() -> None:
    with pytest.raises(InternalCallerRejectedError):
        verify_internal_caller(_request(internal_headers("", "")), {"": ""})

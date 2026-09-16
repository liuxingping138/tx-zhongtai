from __future__ import annotations

from enum import StrEnum


class SecurityClass(StrEnum):
    PUBLIC_AUTH = "public_auth"
    RESOURCE_AUTHORIZED = "resource_authorized"
    INTERNAL = "internal"
    HEALTH = "health"

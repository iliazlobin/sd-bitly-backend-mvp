"""Pydantic schemas for request/response models."""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

BASE62_RE = re.compile(r"^[0-9a-zA-Z]+$")


class CreateURLRequest(BaseModel):
    """Request body for POST /api/urls."""

    long_url: str = Field(..., description="The long URL to shorten")
    custom_alias: str | None = Field(
        default=None,
        max_length=20,
        description="Optional custom short code (1-20 base62 chars)",
    )
    expires_at: datetime | None = Field(
        default=None, description="Optional expiration time (ISO 8601)"
    )

    @model_validator(mode="before")
    @classmethod
    def validate_long_url_present(cls, data: Any) -> Any:
        if isinstance(data, dict) and "long_url" not in data:
            raise ValueError("long_url is required")
        return data

    @field_validator("long_url")
    @classmethod
    def validate_long_url_format(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("long_url is required")
        # Must have a scheme (http/https) and a netloc.
        from urllib.parse import urlparse

        parsed = urlparse(v.strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL format")
        return v.strip()

    @field_validator("custom_alias")
    @classmethod
    def validate_custom_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v == "":
            raise ValueError("custom_alias must be 1-20 base62 chars")
        if not BASE62_RE.match(v):
            raise ValueError("custom_alias must be 1-20 base62 chars")
        return v


class URLResponse(BaseModel):
    """Response returned after creating a short URL."""

    short_code: str
    short_url: str
    long_url: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class StatsResponse(BaseModel):
    """Response for GET /api/urls/{short_code}/stats."""

    short_code: str
    long_url: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}

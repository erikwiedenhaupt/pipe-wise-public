# api/routes_meta.py
"""
Pipewise API – Meta routes
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["meta"], prefix="")

_SERVICE_START = datetime.now(timezone.utc)
_VERSION = os.getenv("PIPEWISE_VERSION", "0.1.0")
_API = os.getenv("PIPEWISE_API_VERSION", "v1")


class HealthzResponse(BaseModel):
    ok: bool
    version: str
    uptime: float = Field(..., description="Uptime in seconds")
    details: Dict[str, Any] = Field(default_factory=dict)


class VersionResponse(BaseModel):
    name: str
    version: str
    build: Optional[str] = None
    api: str
    started_at: Optional[datetime] = None


@router.get("/healthz", response_model=HealthzResponse, summary="Health check")
def healthz() -> HealthzResponse:
    now = datetime.now(timezone.utc)
    return HealthzResponse(
        ok=True,
        version=_VERSION,
        uptime=(now - _SERVICE_START).total_seconds(),
        details={
            "components": {
                "fastapi": "ok",
                "sandbox": "ok",
                "langchain": "stub",
            }
        },
    )


@router.get("/version", response_model=VersionResponse, summary="Service and API version")
def version() -> VersionResponse:
    return VersionResponse(
        name="pipewise-backend",
        version=_VERSION,
        build=os.getenv("PIPEWISE_BUILD", "dev"),
        api=_API,
        started_at=_SERVICE_START,
    )
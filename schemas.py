from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_STATUS = {"SUCCESS", "FAILURE", "UNSTABLE", "ABORTED", "NOT_BUILT"}


class BuildIn(BaseModel):
    job_name: str = Field(min_length=1, max_length=255)
    build_number: int = Field(ge=1)
    status: str
    duration_ms: int = Field(ge=0)
    started_at: datetime
    url: str | None = None
    triggered_by: str | None = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in VALID_STATUS:
            raise ValueError(f"status must be one of {sorted(VALID_STATUS)}")
        return v

    @field_validator("started_at")
    @classmethod
    def _utc_naive(cls, v: datetime) -> datetime:
        return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v


class BuildOut(BuildIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BulkIn(BaseModel):
    builds: list[BuildIn] = Field(max_length=5000)


class SyncIn(BaseModel):
    jobs: list[str] = Field(min_length=1)
    limit: int = Field(100, ge=1, le=1000)

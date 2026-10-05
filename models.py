from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Build(Base):
    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(255))
    build_number: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))  # SUCCESS | FAILURE | UNSTABLE | ABORTED | NOT_BUILT
    duration_ms: Mapped[int] = mapped_column(BigInteger)
    started_at: Mapped[datetime] = mapped_column(DateTime)  # naive UTC
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint("job_name", "build_number", name="uq_job_build"),
        Index("ix_builds_job_started", "job_name", "started_at"),
        Index("ix_builds_started", "started_at"),
        Index("ix_builds_status", "status"),
    )

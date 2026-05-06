import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    markdown_output: Mapped[str | None] = mapped_column(Text)
    slack_ts: Mapped[str | None] = mapped_column(String(100))
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)

    org: Mapped["Organization"] = relationship(back_populates="digests")  # noqa: F821

    __table_args__ = (UniqueConstraint("org_id", "digest_date", name="uq_digest_org_date"),)

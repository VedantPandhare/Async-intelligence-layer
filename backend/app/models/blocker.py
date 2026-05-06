import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Blocker(Base):
    __tablename__ = "blockers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    developer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("developers.id"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocker_type: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    signals: Mapped[dict | None] = mapped_column(JSON)
    intervention_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    intervention_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intervention_content: Mapped[str | None] = mapped_column(Text)

    developer: Mapped["Developer"] = relationship(back_populates="blockers")  # noqa: F821
    org: Mapped["Organization"] = relationship(back_populates="blockers")  # noqa: F821

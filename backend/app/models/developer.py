import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin


class Developer(Base, TimestampMixin):
    __tablename__ = "developers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    github_username: Mapped[str | None] = mapped_column(String(100))
    slack_user_id: Mapped[str | None] = mapped_column(String(100))
    jira_account_id: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    org: Mapped["Organization"] = relationship(back_populates="developers")  # noqa: F821
    activity_events: Mapped[list["ActivityEvent"]] = relationship(back_populates="developer", cascade="all, delete-orphan")  # noqa: F821
    blockers: Mapped[list["Blocker"]] = relationship(back_populates="developer")  # noqa: F821

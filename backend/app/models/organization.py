import uuid
from datetime import time

from sqlalchemy import JSON, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    digest_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    developers: Mapped[list["Developer"]] = relationship(back_populates="org", cascade="all, delete-orphan")  # noqa: F821
    integrations: Mapped[list["Integration"]] = relationship(back_populates="org", cascade="all, delete-orphan")  # noqa: F821
    digests: Mapped[list["Digest"]] = relationship(back_populates="org", cascade="all, delete-orphan")  # noqa: F821
    blockers: Mapped[list["Blocker"]] = relationship(back_populates="org")  # noqa: F821

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Shared declarative base.

    All models inherit from this class so that Alembic's autogenerate can
    discover every table from a single metadata object.
    """


class UUIDPrimaryKeyMixin:
    """
    Mixin that adds a UUID primary key column named ``id``.

    Using UUIDs instead of sequential integers prevents enumeration attacks
    and works naturally in distributed systems.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-100,  # rendered first in CREATE TABLE
    )


class TimestampMixin:
    """
    Mixin that adds ``created_at`` and ``updated_at`` audit columns.

    ``server_default`` ensures the DB sets the value even for inserts that
    bypass the ORM. ``onupdate`` keeps ``updated_at`` accurate on every UPDATE.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=100,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        sort_order=101,
    )

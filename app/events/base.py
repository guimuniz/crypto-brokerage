from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """
    Base class for all domain events.

    Domain events represent facts that have already happened in the domain.
    They are immutable (frozen=True) and carry all data needed by consumers.

    Design notes
    ------------
    - Events are produced by service methods after successful DB commits.
    - They are consumed by background workers, notification services, or
      an event bus (e.g. Redis Streams, Kafka, RabbitMQ).
    - In this shell, events are defined but not yet dispatched. The TODO
      markers indicate where dispatch calls should be added.
    - For reliable delivery, combine with the Outbox Pattern: persist events
      in an ``outbox`` table in the same transaction as the domain changes,
      then dispatch asynchronously from a background worker.

    See: https://microservices.io/patterns/data/domain-event.html
    """

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

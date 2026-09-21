"""本服务的 Outbox 仓储。逻辑在 platform_common，这里只绑定本服务的 ORM model。"""

from __future__ import annotations

from platform_common.outbox import OutboxRepository

from app.domain.models import OutboxEvent

_repository = OutboxRepository(OutboxEvent)

enqueue = _repository.enqueue
claim_pending = _repository.claim_pending
mark_delivered = _repository.mark_delivered
mark_retry = _repository.mark_retry

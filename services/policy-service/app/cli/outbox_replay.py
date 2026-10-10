"""受控重放本服务的 Outbox。默认只重放 dead/failed。用法：python -m app.cli.outbox_replay [--status ...]"""

from __future__ import annotations

import asyncio

from platform_common.outbox import OutboxRepository, run_replay_cli

from app.common.models import OutboxEvent
from app.core.database import SessionLocal

if __name__ == "__main__":
    asyncio.run(run_replay_cli(SessionLocal, OutboxRepository(OutboxEvent), service="policy-service"))

"""鉴权用的资源、动作目录：进程内缓存。

资源和动作只由部署时的 seed（`app.cli.seed`）改写，平时是静态数据。原来每次 authorize 都按编码查一次资源、
再查一次动作，业务服务每个受保护请求都要付这两次查询；现在整份目录缓存在本进程里。

失效方式：

- 到期重读：缓存 `CATALOG_TTL_SECONDS`（60 秒）后下一次判定重读整份目录（两条查询）。seed 跑在另一个进程里
  （`docker-compose exec iam-service python -m app.cli.seed`），这里不会收到通知，靠到期重读跟上；
  要立即生效就重启 iam-service。
- 查不到就重读：新加的资源编码、已有资源上新加的动作在缓存里找不到时立即重读一次
  （`MISS_RELOAD_SECONDS` 内最多一次），seed 一跑完新模块、新动作就能用，不用等满一分钟；
  未知编码反复来也不会每次都打库。
- 同一进程里跑 `sync_catalog`（单测、管理命令）结束时直接清空缓存。

下线、取消发布一个模块最多要等一个缓存周期才在判定里生效；用户的角色、单独授权不在这里缓存，每次判定现查。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import NodeType
from app.repositories import resources as resource_repo

CATALOG_TTL_SECONDS = 60.0
MISS_RELOAD_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class CatalogResource:
    id: uuid.UUID
    code: str
    published: bool
    node_type: str
    # 动作编码 → 所需档位。
    actions: Mapping[str, str]

    @property
    def grantable(self) -> bool:
        """已发布的叶子模块：只有它们上面的授权会生效，与 list_effective_levels 的口径一致。"""

        return self.published and self.node_type == NodeType.RESOURCE


class AuthzCatalog:
    def __init__(
        self,
        *,
        ttl_seconds: float = CATALOG_TTL_SECONDS,
        miss_reload_seconds: float = MISS_RELOAD_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._miss_reload = miss_reload_seconds
        self._clock = clock
        self._entries: dict[str, CatalogResource] = {}
        self._loaded_at: float | None = None

    def invalidate(self) -> None:
        self._entries = {}
        self._loaded_at = None

    def peek(self, code: str) -> CatalogResource | None:
        """读取已加载目录里的条目，不触发重载。供同一次判定内查询关联资源（如智库子库推导我的收藏）使用。"""

        return self._entries.get(code)

    async def resource(self, session: AsyncSession, code: str, action: str | None = None) -> CatalogResource | None:
        """action 给了的话，资源在、动作却不在也算查不到：部署时给已有模块加了新动作，seed 前已经读过目录的话，
        原来要等满一分钟，期间连超管调这个动作都被拒。"""

        if self._age() >= self._ttl:
            await self._load(session)
        entry = self._entries.get(code)
        missing = entry is None or (action is not None and action not in entry.actions)
        if missing and self._age() >= self._miss_reload:
            await self._load(session)
            entry = self._entries.get(code)
        return entry

    def _age(self) -> float:
        """距上次读目录过了多少秒；还没读过算无穷大。"""

        return float("inf") if self._loaded_at is None else self._clock() - self._loaded_at

    async def _load(self, session: AsyncSession) -> None:
        # 两条查询读完整份目录。几个协程同时到期时可能各读一遍，结果相同，不加锁。
        resources = await resource_repo.list_all_resources(session)
        actions = await resource_repo.list_all_actions(session)
        by_resource: dict[uuid.UUID, dict[str, str]] = {}
        for action in actions:
            by_resource.setdefault(action.resource_id, {})[action.action_code] = action.required_level
        entries = {
            row.code: CatalogResource(
                id=row.id,
                code=row.code,
                published=row.published,
                node_type=row.node_type,
                actions=by_resource.get(row.id, {}),
            )
            for row in resources
        }
        # 换整份引用，中间没有 await：并发的判定要么看到旧目录，要么看到新目录，不会看到一半。
        self._entries = entries
        self._loaded_at = self._clock()


catalog = AuthzCatalog()

"""ORM 声明式基类，与引擎/会话创建（app.core.database）分离。

Alembic 迁移环境只需要 `Base.metadata`，不应该因为导入它而触发完整的应用配置校验。
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """审计事件声明式基类。P5 阶段在 app/domain 或专门的 models 模块中定义具体表模型。"""

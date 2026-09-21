"""各业务服务共用的 SQLAlchemy Declarative Base。"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

"""模板类型：按业务线分（政策、客户、招投标），也是授权的单位。

每个类型对应 IAM 里一个资源 `ai.category.<编码>`：查看档能看到这类模板和它们的批量历史，
完整档才能新建、修改、试发、运行。这一层叠加在「提问配置」「批量提问」本身的权限之上。
"""

from __future__ import annotations

from dataclasses import dataclass

from platform_common.errors import ApiError, ErrorCode, PermissionDeniedError

CATEGORIES: dict[str, str] = {"policy": "政策", "customer": "客户", "tender": "招投标"}
DEFAULT_CATEGORY = "policy"
EDIT_LEVEL = "FULL"


def category_resource(code: str) -> str:
    return f"ai.category.{code}"


def category_name(code: str) -> str:
    return CATEGORIES.get(code, code)


def checked_category(value: object) -> str:
    code = str(value or "").strip()
    if code not in CATEGORIES:
        raise ApiError("请选择模板类型（政策、客户或招投标）", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return code


@dataclass(frozen=True)
class CategoryAccess:
    """当前用户能看、能改哪些类型的模板。按 IAM 授权档位算出，一次请求内不变。"""

    readable: frozenset[str]
    editable: frozenset[str]

    @classmethod
    def from_levels(cls, levels: dict[str, str]) -> CategoryAccess:
        granted = {code: levels.get(category_resource(code)) for code in CATEGORIES}
        return cls(
            readable=frozenset(code for code, level in granted.items() if level),
            editable=frozenset(code for code, level in granted.items() if level == EDIT_LEVEL),
        )

    def require_read(self, code: str) -> None:
        if code not in self.readable:
            raise PermissionDeniedError(f"没有查看「{category_name(code)}」类模板的权限")

    def require_edit(self, code: str) -> None:
        if code not in self.editable:
            raise PermissionDeniedError(f"没有编辑或运行「{category_name(code)}」类模板的权限")

    def options(self) -> list[dict[str, object]]:
        """页面上的类型选项：只列能看到的，并标明能不能在这类下新建和修改。"""

        return [
            {"code": code, "name": name, "editable": code in self.editable}
            for code, name in CATEGORIES.items()
            if code in self.readable
        ]


FULL_ACCESS = CategoryAccess(readable=frozenset(CATEGORIES), editable=frozenset(CATEGORIES))

#!/usr/bin/env python3
"""越权访问实测探针。

用低权限账号逐个请求 policy / codebook 的全部业务接口，验证越权是否成立。

安全前提：探针只发起两类请求，不会写入、修改或删除任何业务数据。

1. 只读接口（列表、详情、导出、选项、选项搜索）直接请求。
   详情用随机 UUID，鉴权放行时得到 404。
2. 写接口（新增、编辑、导入、清空、省市区解析）**故意传非法参数**。
   鉴权依赖在 FastAPI 里先于请求体校验执行，所以：
     - 鉴权拒绝 -> 403，请求体根本没被解析；
     - 鉴权放行 -> 422，参数校验拦下，路由函数没执行。
   422 因此是「越权成立」的证据，而不是「接口坏了」。

   JSON 写接口一律只带一个未知字段。所有 Write schema 都声明了
   `extra="forbid"`，未知字段必然 422。不能用空对象 `{}`：
   ScenarioWrite / AreaCodeWrite 的字段全有默认值，空对象是合法载荷，
   鉴权放行时会真的插入一行空记录。
   文件上传接口发送字段名不是 file 的合法 multipart，同样必然 422。

用法：
    uv run --with httpx python tests/authz_probe.py
    uv run --with httpx python tests/authz_probe.py --gateway http://localhost:8090

退出码 0 表示实测结果与预期完全一致；1 表示存在越权或误拒。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

Verdict = Literal["allowed", "denied", "unauthenticated", "unavailable", "error"]

# 探测账号统一口令。这些账号只在开发/隔离栈里存在，跑完会被置为 disabled。
# 新建账号一律带 must_change_password，初始口令必须与最终口令不同才能改密成功。
PROBE_INITIAL_PASSWORD = "Probe#Initial2026"
PROBE_PASSWORD = "Probe#Authz2026"

# 所有 Write schema 都是 extra="forbid"，带未知字段必然在校验阶段 422。
INVALID_BODY = {"__authz_probe_unknown_field__": "1"}

BUSINESS_RESOURCES = [
    "policy.sources",
    "policy.base_tags",
    "policy.interpretations",
    "codebook.policy_types",
    "codebook.scenarios",
    "codebook.area_codes",
]


@dataclass(frozen=True)
class ResourceSpec:
    """一张业务表对外暴露的接口形状。"""

    code: str
    label: str
    base: str
    search_field: str
    has_read: bool = True
    has_purge: bool = False
    has_resolve: bool = False


RESOURCES = [
    ResourceSpec(
        code="policy.sources",
        label="政策信源",
        base="/api/v1/policy/sources",
        search_field="province_name",
        has_purge=True,
    ),
    ResourceSpec(
        code="policy.base_tags",
        label="政策基础标签",
        base="/api/v1/policy/base-tags",
        search_field="province_name",
    ),
    ResourceSpec(
        code="policy.interpretations",
        label="政策解读",
        base="/api/v1/policy/interpretations",
        search_field="industry_l1",
    ),
    ResourceSpec(
        code="codebook.policy_types",
        label="政策类型码表",
        base="/api/v1/codebook/policy-types",
        search_field="type_name",
        has_read=False,
    ),
    ResourceSpec(
        code="codebook.scenarios",
        label="行业场景码表",
        base="/api/v1/codebook/scenarios",
        search_field="industry_l1",
    ),
    ResourceSpec(
        code="codebook.area_codes",
        label="省市区编码",
        base="/api/v1/codebook/area-codes",
        search_field="prov_name",
        has_resolve=True,
    ),
]


@dataclass(frozen=True)
class Endpoint:
    """一次具体的探测请求。`action` 对应 iam 里的动作码。"""

    resource: str
    action: str
    label: str
    method: str
    path: str
    params: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, Any] | None = None
    # 写接口靠「缺少必填项」触发 422，不需要真正构造合法载荷。
    empty_multipart: bool = False


def build_endpoints() -> list[Endpoint]:
    endpoints: list[Endpoint] = []
    for spec in RESOURCES:
        endpoints.append(Endpoint(spec.code, "list", f"{spec.label} 列表", "GET", spec.base))
        endpoints.append(
            Endpoint(spec.code, "list", f"{spec.label} 筛选项预览", "GET", f"{spec.base}/options")
        )
        endpoints.append(
            Endpoint(
                spec.code,
                "list",
                f"{spec.label} 筛选项搜索",
                "GET",
                f"{spec.base}/options/search",
                params={"field": spec.search_field, "q": "探"},
            )
        )
        endpoints.append(
            Endpoint(spec.code, "export", f"{spec.label} 导出", "GET", f"{spec.base}/export")
        )
        if spec.has_read:
            endpoints.append(
                Endpoint(
                    spec.code,
                    "read",
                    f"{spec.label} 详情",
                    "GET",
                    f"{spec.base}/{uuid.uuid4()}",
                )
            )
        endpoints.append(
            Endpoint(
                spec.code, "create", f"{spec.label} 新增", "POST", spec.base, json_body=INVALID_BODY
            )
        )
        endpoints.append(
            Endpoint(
                spec.code,
                "update",
                f"{spec.label} 编辑",
                "PATCH",
                f"{spec.base}/{uuid.uuid4()}",
                json_body=INVALID_BODY,
            )
        )
        endpoints.append(
            Endpoint(
                spec.code,
                "import",
                f"{spec.label} 导入",
                "POST",
                f"{spec.base}/import",
                empty_multipart=True,
            )
        )
        if spec.has_resolve:
            endpoints.append(
                Endpoint(
                    spec.code,
                    "resolve",
                    f"{spec.label} 解析",
                    "POST",
                    f"{spec.base}/resolve",
                    empty_multipart=True,
                )
            )
        if spec.has_purge:
            # 载荷同样非法：即使鉴权被绕过，路由函数也不会执行，不可能真的清表。
            endpoints.append(
                Endpoint(
                    spec.code,
                    "purge",
                    f"{spec.label} 清空",
                    "POST",
                    f"{spec.base}/clear",
                    json_body=INVALID_BODY,
                )
            )
    return endpoints


READ_ACTIONS = {"list", "read", "export", "resolve"}
WRITE_ACTIONS = {"create", "update", "import"}


@dataclass
class ProbeAccount:
    """一个探测身份：角色授权 + 期望结果的判定规则。"""

    key: str
    username: str
    display_name: str
    role_code: str
    role_name: str
    grants: dict[str, str]
    summary: str
    change_password: bool = True
    token: str | None = None

    def expect(self, endpoint: Endpoint) -> Verdict:
        if not self.change_password:
            # 未修改初始密码的账号在 require_authenticated 阶段就被拦下。
            return "denied"
        level = self.grants.get(endpoint.resource, "NONE")
        if level == "NONE":
            return "denied"
        if endpoint.action == "purge":
            # purge 额外要求内置 superadmin 角色，探测账号都不是。
            return "denied"
        if endpoint.action in READ_ACTIONS:
            return "allowed" if level in {"READ", "FULL"} else "denied"
        return "allowed" if level == "FULL" else "denied"


FULL_READ = dict.fromkeys(BUSINESS_RESOURCES, "READ")

ACCOUNTS = [
    ProbeAccount(
        key="reader",
        username="probe.reader",
        display_name="越权探测-只读",
        role_code="probe_reader",
        role_name="越权探测-全表只读",
        grants=FULL_READ,
        summary="六张业务表均为 READ",
    ),
    ProbeAccount(
        key="scoped",
        username="probe.scoped",
        display_name="越权探测-单表可写",
        role_code="probe_scoped",
        role_name="越权探测-仅信源可写",
        grants={"policy.sources": "FULL"},
        summary="仅 policy.sources 为 FULL，其余无授权",
    ),
    ProbeAccount(
        key="nogrant",
        username="probe.nogrant",
        display_name="越权探测-无授权",
        role_code="probe_nogrant",
        role_name="越权探测-空角色",
        grants={},
        summary="有账号有角色，但角色没有任何授权",
    ),
    ProbeAccount(
        key="pending",
        username="probe.pending",
        display_name="越权探测-未改初始密码",
        role_code="probe_reader",
        role_name="越权探测-全表只读",
        grants=FULL_READ,
        summary="授权同只读账号，但未修改初始密码",
        change_password=False,
    ),
]


@dataclass
class Outcome:
    account: str
    endpoint: Endpoint
    expected: Verdict
    actual: Verdict
    status: int
    detail: str

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


def classify(status: int) -> Verdict:
    if status == 401:
        return "unauthenticated"
    if status == 403:
        return "denied"
    if status == 503:
        return "unavailable"
    if status in {200, 201, 204, 404, 409, 422}:
        # 404/409/422 都说明鉴权已放行，请求被业务或参数校验拦下。
        return "allowed"
    return "error"


class AdminClient:
    """用超级管理员账号准备探测用的角色和账号。"""

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        self._client = client
        self._token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}"}
        csrf = self._client.cookies.get("csrf_token")
        if csrf:
            headers["X-CSRF-Token"] = csrf
        return headers

    async def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, headers=self._headers(), **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} 返回 {response.status_code}: {response.text[:400]}")
        return response

    async def ensure_role(self, code: str, name: str, grants: dict[str, str]) -> str:
        listing = await self.call("GET", "/api/v1/system/roles", params={"page_size": 100})
        existing = {
            item["code"]: item for item in listing.json()["data"]["items"]
        }
        if code in existing:
            role_id = existing[code]["id"]
        else:
            created = await self.call("POST", "/api/v1/system/roles", json={"code": code, "name": name})
            role_id = created.json()["data"]["id"]
        current = await self.call("GET", f"/api/v1/system/roles/{role_id}/grants")
        await self.call(
            "PUT",
            f"/api/v1/system/roles/{role_id}/grants",
            json={
                "version": current.json()["data"]["role"]["version"],
                "grants": [
                    {"resource_code": resource, "level": level} for resource, level in grants.items()
                ],
            },
        )
        return role_id

    async def ensure_user(self, username: str, display_name: str, role_id: str) -> tuple[str, str]:
        """返回 (user_id, 可登录密码)。已存在的账号走 reset-password 拿临时密码。"""

        listing = await self.call(
            "GET", "/api/v1/system/users", params={"username": username, "page_size": 100}
        )
        match = next(
            (item for item in listing.json()["data"]["items"] if item["username"] == username), None
        )
        if match is None:
            created = await self.call(
                "POST",
                "/api/v1/system/users",
                json={
                    "username": username,
                    "display_name": display_name,
                    "password": PROBE_INITIAL_PASSWORD,
                },
            )
            user = created.json()["data"]["user"]
            password = PROBE_INITIAL_PASSWORD
        else:
            user = match
            if user["status"] != "active":
                updated = await self.call(
                    "PATCH",
                    f"/api/v1/system/users/{user['id']}",
                    json={"status": "active", "version": user["version"]},
                )
                user = updated.json()["data"]
            reset = await self.call("POST", f"/api/v1/system/users/{user['id']}/reset-password")
            password = reset.json()["data"]["temporary_password"]
            refreshed = await self.call("GET", f"/api/v1/system/users/{user['id']}")
            user = refreshed.json()["data"]
        await self.call(
            "PUT",
            f"/api/v1/system/users/{user['id']}/roles",
            json={"role_ids": [role_id], "version": user["version"]},
        )
        return user["id"], password

    async def disable_user(self, username: str) -> None:
        listing = await self.call(
            "GET", "/api/v1/system/users", params={"username": username, "page_size": 100}
        )
        match = next(
            (item for item in listing.json()["data"]["items"] if item["username"] == username), None
        )
        if match is None or match["status"] != "active":
            return
        await self.call(
            "PATCH",
            f"/api/v1/system/users/{match['id']}",
            json={"status": "disabled", "version": match["version"]},
        )


async def login(client: httpx.AsyncClient, username: str, password: str) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    if response.status_code != 200:
        raise RuntimeError(f"{username} 登录失败 {response.status_code}: {response.text[:400]}")
    return response.json()["data"]


async def change_password(client: httpx.AsyncClient, token: str, old: str, new: str) -> str:
    response = await client.put(
        "/api/v1/auth/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": old, "new_password": new},
    )
    if response.status_code != 200:
        raise RuntimeError(f"改密失败 {response.status_code}: {response.text[:400]}")
    return response.json()["data"]["access_token"]


async def probe(
    client: httpx.AsyncClient, token: str | None, endpoint: Endpoint
) -> tuple[int, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs: dict[str, Any] = {"params": endpoint.params or None}
    if endpoint.json_body is not None:
        kwargs["json"] = endpoint.json_body
    if endpoint.empty_multipart:
        # 是合法 multipart，但字段名不是 file，鉴权放行时由必填校验返回 422。
        kwargs["files"] = {"not_the_file_field": ("probe.txt", b"probe", "text/plain")}
    response = await client.request(endpoint.method, endpoint.path, headers=headers, **kwargs)
    detail = ""
    if response.status_code >= 400:
        try:
            body = response.json()
            detail = str(body.get("message") or body.get("detail") or "")[:160]
        except Exception:
            detail = response.text[:160]
    return response.status_code, detail


async def run(gateway: str, admin_user: str, admin_password: str, keep_enabled: bool) -> int:
    endpoints = build_endpoints()
    outcomes: list[Outcome] = []

    async with httpx.AsyncClient(base_url=gateway, timeout=30.0) as admin_http:
        admin_data = await login(admin_http, admin_user, admin_password)
        admin = AdminClient(admin_http, admin_data["access_token"])
        print(f"== 准备探测角色与账号（网关 {gateway}）")

        roles: dict[str, str] = {}
        for account in ACCOUNTS:
            if account.role_code not in roles:
                roles[account.role_code] = await admin.ensure_role(
                    account.role_code, account.role_name, account.grants
                )
            print(f"   - 角色 {account.role_code}: {account.summary}")

        for account in ACCOUNTS:
            _, password = await admin.ensure_user(
                account.username, account.display_name, roles[account.role_code]
            )
            async with httpx.AsyncClient(base_url=gateway, timeout=30.0) as user_http:
                data = await login(user_http, account.username, password)
                token = data["access_token"]
                if account.change_password:
                    token = await change_password(user_http, token, password, PROBE_PASSWORD)
                else:
                    assert data["must_change_password"], f"{account.username} 应处于待改密状态"
            account.token = token
            print(f"   - 账号 {account.username} 就绪")

        print(f"\n== 逐个接口实测（{len(endpoints)} 个接口 × {len(ACCOUNTS) + 2} 个身份）")
        async with httpx.AsyncClient(base_url=gateway, timeout=60.0) as probe_http:
            for account in ACCOUNTS:
                for endpoint in endpoints:
                    status, detail = await probe(probe_http, account.token, endpoint)
                    outcomes.append(
                        Outcome(
                            account.username,
                            endpoint,
                            account.expect(endpoint),
                            classify(status),
                            status,
                            detail,
                        )
                    )

            # 匿名与伪造令牌：任何业务接口都必须是 401。
            forged = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIiwidHlwIjoiSldUIn0.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAiLCJzaWQiOiIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAiLCJpc3MiOiJ0eC16aG9uZ3RhaS1pYW0iLCJhdWQiOiJ0eC16aG9uZ3RhaSIsImlhdCI6MTc4OTk2ODQ5NCwiZXhwIjo0MDcwOTA4ODAwLCJqdGkiOiJkZWFkYmVlZiJ9.ZmFrZS1zaWduYXR1cmU"
            for label, token in (("<匿名>", None), ("<伪造令牌>", forged)):
                for endpoint in endpoints:
                    status, detail = await probe(probe_http, token, endpoint)
                    outcomes.append(
                        Outcome(label, endpoint, "unauthenticated", classify(status), status, detail)
                    )

        if not keep_enabled:
            print("\n== 收尾：把探测账号置为 disabled")
            for account in ACCOUNTS:
                await admin.disable_user(account.username)

    return report(outcomes)


def report(outcomes: list[Outcome]) -> int:
    by_account: dict[str, list[Outcome]] = {}
    for item in outcomes:
        by_account.setdefault(item.account, []).append(item)

    print("\n== 实测结果")
    for account, items in by_account.items():
        bad = [item for item in items if not item.ok]
        flag = "OK" if not bad else f"异常 {len(bad)}"
        print(f"\n-- {account}（{len(items)} 项，{flag}）")
        for item in items:
            mark = " " if item.ok else "!"
            print(
                f"  {mark} [{item.status:>3}] {item.actual:<16} 期望 {item.expected:<16}"
                f" {item.endpoint.method:<5} {item.endpoint.path}"
                f"  ({item.endpoint.resource}.{item.endpoint.action})"
                + (f"  {item.detail}" if not item.ok and item.detail else "")
            )

    failures = [item for item in outcomes if not item.ok]
    escalations = [
        item for item in failures if item.expected == "denied" and item.actual == "allowed"
    ]
    print("\n== 汇总")
    print(f"   实测请求 {len(outcomes)} 次，与预期不符 {len(failures)} 次，其中越权成立 {len(escalations)} 次")
    if escalations:
        print("\n   以下请求本应被拒绝但实际放行：")
        for item in escalations:
            print(
                f"     {item.account} {item.endpoint.method} {item.endpoint.path}"
                f" -> {item.status}"
            )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="越权访问实测探针")
    parser.add_argument("--gateway", default=os.environ.get("PROBE_GATEWAY", "http://localhost:8080"))
    parser.add_argument("--admin-user", default=os.environ.get("PROBE_ADMIN_USER", "admin"))
    parser.add_argument("--admin-password", default=os.environ.get("PROBE_ADMIN_PASSWORD", ""))
    parser.add_argument(
        "--keep-enabled",
        action="store_true",
        help="跑完保留探测账号为启用状态（默认置为 disabled）",
    )
    args = parser.parse_args()
    if not args.admin_password:
        print("请通过 --admin-password 或 PROBE_ADMIN_PASSWORD 提供管理员密码", file=sys.stderr)
        return 2
    try:
        return asyncio.run(
            run(args.gateway, args.admin_user, args.admin_password, args.keep_enabled)
        )
    except RuntimeError as exc:
        print(f"探测中断：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

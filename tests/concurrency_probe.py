#!/usr/bin/env python3
"""事务、幂等与并发实测探针。

**只能指向 P6 隔离栈**：本脚本会真实新增和修改业务数据，跑完数据留在隔离库里，
靠 `make p6-down` 连卷一起销毁。脚本启动时会检查网关端口不是开发栈的 8080。

覆盖四件事：

1. 乐观锁并发：多个客户端拿同一个 version 同时改同一条，只应有一个成功，
   其余必须 409。若出现多个 200，说明 version 比对存在 TOCTOU 窗口，更新会静默丢失。
2. 重复提交：同一份新增载荷并发提交多次，只应落一条。
3. 导入原子性：两个相同的导入并发执行，最终行数必须等于「一份文件的行数」，
   不允许出现介于 0 和文件行数之间的部分写入。
4. 导入全批退回：文件里掺一行非法数据，整批必须零写入。

用法：
    uv run --with httpx --with openpyxl python tests/concurrency_probe.py \
        --gateway http://localhost:8090 --admin-user p6admin --admin-password P6accept.ok.1
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from openpyxl import Workbook

SOURCES = "/api/v1/policy/sources"

# 与 services/policy-service/app/domain/fields.py 的 SOURCE_COLUMNS 表头一致。
SOURCE_HEADERS = [
    "内部唯一id",
    "网站编码",
    "省份",
    "省份编码",
    "地市",
    "地市编码",
    "区县",
    "区县编码",
    "网站名称",
    "网站梳理和抓取的优先级",
    "链接",
    "标签",
    "数据类型",
    "所属部门",
]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def build_source_sheet(site_names: list[str]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(SOURCE_HEADERS)
    for name in site_names:
        row = {"省份": "北京市", "省份编码": "110000", "网站名称": name, "标签": "并发探测"}
        sheet.append([row.get(header, "") for header in SOURCE_HEADERS])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class Api:
    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        self._client = client
        self._token = token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.request(method, path, headers=self.headers, **kwargs)

    async def expect(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} 返回 {response.status_code}: {response.text[:300]}")
        return response.json()["data"]


async def sign_in(client: httpx.AsyncClient, username: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError(f"登录失败 {response.status_code}: {response.text[:300]}")
    data = response.json()["data"]
    token: str = data["access_token"]
    if data["must_change_password"]:
        # P6 的初始管理员带强制改密标记，不改密拿不到业务权限。
        changed = await client.put(
            "/api/v1/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": password, "new_password": f"{password}.probe1"},
        )
        if changed.status_code != 200:
            raise RuntimeError(f"改密失败 {changed.status_code}: {changed.text[:300]}")
        token = changed.json()["data"]["access_token"]
    return token


async def count_sources(api: Api, *, tag: str) -> int:
    data = await api.expect("GET", SOURCES, params={"tag": tag, "page_size": 1})
    return int(data["total"])


async def probe_optimistic_lock_round(api: Api, concurrency: int) -> tuple[int, int, int, int]:
    """跑一轮同版本并发更新，返回 (起始版本, 成功数, 冲突数, 最终版本)。"""

    created = await api.expect(
        "POST",
        SOURCES,
        json={
            "site_name": f"乐观锁探测-{uuid.uuid4().hex[:8]}",
            "province_name": "北京市",
            "province_code": "110000",
            "tag": "并发探测",
        },
    )
    item_id, version = created["id"], created["version"]

    async def writer(index: int) -> int:
        response = await api.request(
            "PATCH",
            f"{SOURCES}/{item_id}",
            json={
                "version": version,
                "site_name": created["site_name"],
                "province_name": "北京市",
                "province_code": "110000",
                "tag": "并发探测",
                "department": f"并发写入-{index}",
            },
        )
        return response.status_code

    statuses = await asyncio.gather(*(writer(i) for i in range(concurrency)))
    accepted = sum(1 for code in statuses if code == 200)
    conflicts = sum(1 for code in statuses if code == 409)
    final = await api.expect("GET", f"{SOURCES}/{item_id}")
    return version, accepted, conflicts, int(final["version"])


async def probe_optimistic_lock(api: Api, concurrency: int, rounds: int) -> list[Check]:
    results = [await probe_optimistic_lock_round(api, concurrency) for _ in range(rounds)]
    worst = max(results, key=lambda item: item[1])
    lost_updates = [
        (start, accepted, final)
        for start, accepted, _conflicts, final in results
        if final != start + accepted
    ]
    summary = ", ".join(
        f"第{index + 1}轮 200×{accepted}/409×{conflicts}" for index, (_s, accepted, conflicts, _f) in enumerate(results)
    )
    return [
        Check(
            "乐观锁：同版本并发更新每轮只应有一个成功",
            worst[1] == 1,
            f"{rounds} 轮 × {concurrency} 并发：{summary}",
        ),
        Check(
            "乐观锁：版本号增量必须等于成功次数（不等即有更新被静默覆盖）",
            not lost_updates,
            "全部轮次版本号自增与成功次数一致"
            if not lost_updates
            else f"以下轮次出现丢失更新（起始/成功/最终）: {lost_updates}",
        ),
    ]


async def probe_duplicate_submit(api: Api, concurrency: int) -> list[Check]:
    site_name = f"重复提交探测-{uuid.uuid4().hex[:8]}"
    payload = {
        "site_name": site_name,
        "province_name": "北京市",
        "province_code": "110000",
        "tag": "并发探测",
    }

    async def submit() -> int:
        response = await api.request("POST", SOURCES, json=payload)
        return response.status_code

    statuses = await asyncio.gather(*(submit() for _ in range(concurrency)))
    listed = await api.expect("GET", SOURCES, params={"site_name": site_name, "page_size": 100})
    created = [code for code in statuses if code == 201]
    return [
        Check(
            "重复提交：并发提交同一份新增只应落一条",
            listed["total"] == 1,
            f"{concurrency} 次并发提交，201×{len(created)}，库里实际 {listed['total']} 条，"
            f"状态码分布 {sorted(statuses)}",
        ),
        Check(
            "重复提交：被挡下的请求应返回 409 而不是 500",
            all(code in {201, 409} for code in statuses),
            f"状态码分布 {sorted(statuses)}",
        ),
    ]


async def probe_import_atomicity(api: Api, rows: int) -> list[Check]:
    batch = uuid.uuid4().hex[:8]
    site_names = [f"导入原子性-{batch}-{i:03d}" for i in range(rows)]
    content = build_source_sheet(site_names)
    before = await count_sources(api, tag="并发探测")

    async def importer() -> tuple[int, dict[str, Any] | None]:
        response = await api.request(
            "POST",
            f"{SOURCES}/import",
            files={"file": ("sources.xlsx", content, "application/octet-stream")},
        )
        if response.status_code == 200 and response.headers.get("content-type", "").startswith(
            "application/json"
        ):
            return response.status_code, response.json().get("data")
        return response.status_code, None

    results = await asyncio.gather(importer(), importer())
    after = await count_sources(api, tag="并发探测")
    written = after - before
    statuses = [code for code, _ in results]
    return [
        Check(
            "导入原子性：两个相同导入并发执行后只应写入一份",
            written == rows,
            f"文件 {rows} 行，并发两次导入后实际新增 {written} 行，状态码 {statuses}",
        ),
        Check(
            "导入原子性：失败的那次不得留下部分数据",
            written in {0, rows},
            f"实际新增 {written} 行（允许 0 或 {rows}，介于两者之间即为部分写入）",
        ),
    ]


async def probe_import_rejects_whole_batch(api: Api, rows: int) -> list[Check]:
    batch = uuid.uuid4().hex[:8]
    site_names = [f"全批退回-{batch}-{i:03d}" for i in range(rows)]
    # 末尾掺一行网站名称为空的非法数据，整批应被退回。
    content = build_source_sheet([*site_names, ""])

    before = await count_sources(api, tag="并发探测")
    response = await api.request(
        "POST",
        f"{SOURCES}/import",
        files={"file": ("sources.xlsx", content, "application/octet-stream")},
    )
    after = await count_sources(api, tag="并发探测")
    return [
        Check(
            "全批退回：含一行非法数据时整批零写入",
            after == before,
            f"导入前 {before} 行，导入后 {after} 行，响应 {response.status_code}",
        )
    ]


async def run(gateway: str, admin_user: str, admin_password: str, concurrency: int, rounds: int) -> int:
    if gateway.rstrip("/").endswith(":8080"):
        print("拒绝执行：本脚本会写入业务数据，只能指向 P6 隔离栈。", file=sys.stderr)
        return 2

    async with httpx.AsyncClient(base_url=gateway, timeout=120.0) as client:
        token = await sign_in(client, admin_user, admin_password)
        api = Api(client, token)

        checks: list[Check] = []
        print("== 乐观锁并发")
        checks += await probe_optimistic_lock(api, concurrency, rounds)
        print("== 重复提交")
        checks += await probe_duplicate_submit(api, concurrency)
        print("== 导入原子性")
        checks += await probe_import_atomicity(api, rows=40)
        print("== 导入全批退回")
        checks += await probe_import_rejects_whole_batch(api, rows=20)

    print("\n== 实测结果")
    for check in checks:
        print(f"  {'通过' if check.passed else '失败'}  {check.name}\n        {check.detail}")
    failed = [check for check in checks if not check.passed]
    print(f"\n== 汇总：{len(checks)} 项检查，失败 {len(failed)} 项")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="事务、幂等与并发实测探针（仅限 P6 隔离栈）")
    parser.add_argument("--gateway", default=os.environ.get("P6_GATEWAY", "http://localhost:8090"))
    parser.add_argument("--admin-user", default=os.environ.get("PROBE_ADMIN_USER", "p6admin"))
    parser.add_argument("--admin-password", default=os.environ.get("PROBE_ADMIN_PASSWORD", ""))
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=1, help="乐观锁并发跑几轮")
    args = parser.parse_args()
    if not args.admin_password:
        print("请通过 --admin-password 或 PROBE_ADMIN_PASSWORD 提供管理员密码", file=sys.stderr)
        return 2
    try:
        return asyncio.run(
            run(args.gateway, args.admin_user, args.admin_password, args.concurrency, args.rounds)
        )
    except RuntimeError as exc:
        print(f"探测中断：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

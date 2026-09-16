"""P6 隔离栈验收：A01-A18 中可通过网关/数据库完成的场景。"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from typing import Any


class Failed(RuntimeError):
    pass


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.token = ""
        self.csrf = ""

    def call(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        *,
        token: str | None = None,
        extra_headers: dict[str, str] | None = None,
        origin: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        use_token = self.token if token is None else token
        if use_token:
            headers["Authorization"] = f"Bearer {use_token}"
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        if origin:
            headers["Origin"] = origin
        if extra_headers:
            headers.update(extra_headers)
        body = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=20) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw[:120]}
            return exc.code, payload

    def login(self, username: str, password: str) -> dict[str, Any]:
        status, body = self.call("POST", "/api/v1/auth/login", {"username": username, "password": password})
        if status != 200:
            raise Failed(f"login {username} -> {status} {body}")
        data = body.get("data") or {}
        self.token = str(data.get("access_token") or "")
        self.csrf = self._cookie("csrf_token")
        return data

    def _cookie(self, name: str) -> str:
        for cookie in self.jar:
            if cookie.name == name:
                return cookie.value or ""
        return ""


def expect(cond: bool, message: str) -> None:
    if not cond:
        raise Failed(message)


def compose_exec(compose: list[str], *args: str) -> str:
    return subprocess.check_output([*compose, "exec", "-T", *args], text=True)


def wait_gateway(base: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = Api(base).call("GET", "/api/v1/auth/csrf")
            if status == 200:
                return
        except Exception:
            time.sleep(1)
    raise Failed("gateway not ready")


def change_password(api: Api, old: str, new: str) -> None:
    status, body = api.call("PUT", "/api/v1/auth/password", {"old_password": old, "new_password": new})
    expect(status == 200, f"change password {status} {body}")
    data = body.get("data") or {}
    api.token = str(data.get("access_token") or api.token)
    api.csrf = api._cookie("csrf_token") or api.csrf


def run() -> None:
    base = os.environ["P6_GATEWAY"]
    compose = os.environ["P6_COMPOSE"].split()
    admin_user = os.environ.get("ADMIN_USERNAME", "p6admin")
    admin_password = os.environ["ADMIN_PASSWORD"]
    admin_new = os.environ.get("P6_ADMIN_NEW_PASSWORD", "P6accept.ok.2")
    runtime_path = os.environ.get("P6_RUNTIME_FILE", "")
    origin = base

    wait_gateway(base)
    results: list[str] = []

    # A01
    api = Api(base)
    status, body = api.call("GET", "/api/v1/system/users")
    expect(status == 401, f"A01 expected 401 got {status} {body}")
    results.append("A01 ok")

    # bootstrap admin (must change password)
    admin = Api(base)
    first = admin.login(admin_user, admin_password)
    if first.get("must_change_password"):
        change_password(admin, admin_password, admin_new)
        admin_password = admin_new
    if runtime_path:
        with open(runtime_path, "w", encoding="utf-8") as handle:
            handle.write(f"ADMIN_USERNAME={admin_user}\nADMIN_PASSWORD={admin_password}\n")

    # A08: first-login restricted
    created, _ = admin.call(
        "POST",
        "/api/v1/system/users",
        {"username": "p6first", "display_name": "首登用户", "password": "P6first.ok.1"},
    )
    expect(created == 201, f"create p6first {created}")
    first_user = Api(base)
    first_user.login("p6first", "P6first.ok.1")
    denied, body = first_user.call("GET", "/api/v1/system/users")
    expect(denied == 403, f"A08 expected 403 got {denied} {body}")
    results.append("A08 ok")
    change_password(first_user, "P6first.ok.1", "P6first.ok.2")

    # A02 / A03 / A04: READ role on users only
    role_status, role_body = admin.call("POST", "/api/v1/system/roles", {"code": "p6reader", "name": "P6只读"})
    expect(role_status == 201, f"create role {role_status} {role_body}")
    role = (role_body.get("data") or {})
    role_id = role["id"]
    grants, gbody = admin.call(
        "PUT",
        f"/api/v1/system/roles/{role_id}/grants",
        {"version": role["version"], "grants": [{"resource_code": "system.users", "level": "READ"}]},
    )
    expect(grants == 200, f"grants {grants} {gbody}")
    unpublished, ubody = admin.call(
        "PUT",
        f"/api/v1/system/roles/{role_id}/grants",
        {
            "version": (gbody.get("data") or {}).get("role", {}).get("version", role["version"] + 1),
            "grants": [{"resource_code": "policy.sources", "level": "READ"}],
        },
    )
    expect(unpublished == 403, f"A09 grant unpublished {unpublished} {ubody}")
    results.append("A09 ok")

    user_status, user_body = admin.call(
        "POST",
        "/api/v1/system/users",
        {"username": "p6reader1", "display_name": "P6读者", "password": "P6read.ok.1"},
    )
    expect(user_status == 201, f"create reader {user_status} {user_body}")
    reader_id = (user_body.get("data") or {})["user"]["id"]
    reader_ver = (user_body.get("data") or {})["user"]["version"]
    assigned, _ = admin.call(
        "PUT",
        f"/api/v1/system/users/{reader_id}/roles",
        {"role_ids": [role_id], "version": reader_ver},
    )
    expect(assigned == 200, f"assign reader {assigned}")
    change_password_login = Api(base)
    change_password_login.login("p6reader1", "P6read.ok.1")
    change_password(change_password_login, "P6read.ok.1", "P6read.ok.2")
    listed, lbody = change_password_login.call("GET", "/api/v1/system/users")
    expect(listed == 200, f"A02 list {listed}")
    wrote, wbody = change_password_login.call(
        "POST", "/api/v1/system/users", {"username": "shouldfail", "display_name": "x"}
    )
    expect(wrote == 403, f"A02 write {wrote} {wbody}")
    roles, rbody = change_password_login.call("GET", "/api/v1/system/roles")
    expect(roles == 403, f"A03 roles {roles} {rbody}")
    results.append("A02 ok")
    results.append("A03 ok")

    # A04 disable role then reader loses access
    role_latest, role_now = admin.call("GET", f"/api/v1/system/roles/{role_id}")
    expect(role_latest == 200, "load role")
    version = (role_now.get("data") or {})["version"]
    disabled, _ = admin.call(
        "PATCH",
        f"/api/v1/system/roles/{role_id}",
        {"status": "disabled", "version": version},
    )
    expect(disabled == 200, f"disable role {disabled}")
    lost, _ = change_password_login.call("GET", "/api/v1/system/users")
    expect(lost == 403, f"A04 after disable role {lost}")
    results.append("A04 ok")
    admin.call("PATCH", f"/api/v1/system/roles/{role_id}", {"status": "active", "version": version + 1})

    # A05 disable user
    reader_row, reader_body = admin.call("GET", f"/api/v1/system/users/{reader_id}")
    expect(reader_row == 200, "reader get")
    rver = (reader_body.get("data") or {})["version"]
    admin.call("PATCH", f"/api/v1/system/users/{reader_id}", {"status": "disabled", "version": rver})
    old_token = change_password_login.token
    ghost = Api(base)
    ghost.token = old_token
    stale, _ = ghost.call("GET", "/api/v1/system/users")
    expect(stale == 401, f"A05 stale jwt {stale}")
    results.append("A05 ok")

    # A06 bad tokens
    for token in ("not-a-jwt", "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0."):
        bad = Api(base)
        bad.token = token
        status, _ = bad.call("GET", "/api/v1/auth/me")
        expect(status == 401, f"A06 {token[:12]} -> {status}")
    results.append("A06 ok")

    # A07 refresh replay
    left = Api(base)
    left.login(admin_user, admin_password)
    refresh_one, _ = left.call("POST", "/api/v1/auth/refresh", origin=origin)
    expect(refresh_one == 200, f"refresh {refresh_one}")
    replay, _ = left.call("POST", "/api/v1/auth/refresh", origin=origin)
    # cookie already rotated; replaying requires keeping old cookie. Use a second jar copy:
    # After first refresh, old cookie is replaced. Rebuild by capturing cookie before refresh.
    results.append("A07 refresh-rotate ok")

    replay_api = Api(base)
    replay_api.login(admin_user, admin_password)
    old_refresh = replay_api._cookie("refresh_token")
    rotated, _ = replay_api.call("POST", "/api/v1/auth/refresh", origin=origin)
    expect(rotated == 200, f"A07 rotate {rotated}")
    replay_api.csrf = replay_api._cookie("csrf_token")
    for cookie in list(replay_api.jar):
        if cookie.name == "refresh_token":
            cookie.value = old_refresh
    replayed, rbody = replay_api.call("POST", "/api/v1/auth/refresh", origin=origin)
    expect(replayed == 401, f"A07 replay {replayed} {rbody}")
    results.append("A07 ok")

    # A14 forged header / internal
    forged = Api(base)
    status, body = forged.call("GET", "/api/v1/system/users", extra_headers={"X-User-Id": "1", "X-Roles": "superadmin"})
    expect(status == 401, f"A14 forged {status}")
    internal, ibody = forged.call("POST", "/internal/v1/audit/events", {"event_id": "11111111-1111-1111-1111-111111111111", "occurred_at": "2026-01-01T00:00:00Z", "outcome": "success"})
    expect(internal not in {200, 201}, f"A14 internal exposed {internal} {ibody}")
    results.append("A14 ok")

    # A15 version conflict
    me_roles, role_list = admin.call("GET", f"/api/v1/system/roles/{role_id}")
    expect(me_roles == 200, "role for 409")
    ver = (role_list.get("data") or {})["version"]
    first_ok, _ = admin.call(
        "PUT",
        f"/api/v1/system/roles/{role_id}/grants",
        {"version": ver, "grants": [{"resource_code": "system.users", "level": "READ"}]},
    )
    second, sbody = admin.call(
        "PUT",
        f"/api/v1/system/roles/{role_id}/grants",
        {"version": ver, "grants": [{"resource_code": "system.users", "level": "FULL"}]},
    )
    expect(first_ok == 200 and second == 409, f"A15 {first_ok}/{second} {sbody}")
    results.append("A15 ok")

    # A10 last admin: disable the only extra superadmin attempt on admin itself
    users_page, users_body = admin.call("GET", "/api/v1/system/users?page_size=100")
    admin_id = None
    for item in (users_body.get("data") or {}).get("items") or []:
        if item.get("username") == admin_user:
            admin_id = item["id"]
            admin_ver = item["version"]
    expect(admin_id is not None, "admin id")
    protect, pbody = admin.call(
        "PATCH",
        f"/api/v1/system/users/{admin_id}",
        {"status": "disabled", "version": admin_ver},
    )
    expect(protect == 403, f"A10 disable self last admin {protect} {pbody}")
    results.append("A10 ok")

    # A13 rollback: duplicate username should not add a second created event
    before = compose_exec(
        compose,
        "postgres",
        "psql",
        "-U",
        os.environ["POSTGRES_SUPERUSER"],
        "-d",
        os.environ["IAM_DB_NAME"],
        "-tAc",
        "SELECT count(*) FROM iam_outbox WHERE event_type='iam.user.created';",
    ).strip()
    dup, _ = admin.call("POST", "/api/v1/system/users", {"username": "p6first", "display_name": "重复"})
    expect(dup in {409, 400}, f"A13 dup {dup}")
    after = compose_exec(
        compose,
        "postgres",
        "psql",
        "-U",
        os.environ["POSTGRES_SUPERUSER"],
        "-d",
        os.environ["IAM_DB_NAME"],
        "-tAc",
        "SELECT count(*) FROM iam_outbox WHERE event_type='iam.user.created';",
    ).strip()
    expect(before == after, f"A13 outbox grew {before}->{after}")
    results.append("A13 ok")

    # A12 audit down / recover
    subprocess.check_call([*compose, "stop", "audit-service"])
    fail_login = Api(base)
    status, _ = fail_login.call("POST", "/api/v1/auth/login", {"username": "nobody-p6", "password": "wrong-pass"})
    expect(status == 401, f"login during audit down {status}")
    pending = compose_exec(
        compose,
        "postgres",
        "psql",
        "-U",
        os.environ["POSTGRES_SUPERUSER"],
        "-d",
        os.environ["IAM_DB_NAME"],
        "-tAc",
        "SELECT count(*) FROM iam_outbox WHERE status<>'delivered';",
    ).strip()
    expect(int(pending) >= 1, f"A12 expected unfinished {pending}")
    subprocess.check_call([*compose, "start", "audit-service"])
    subprocess.check_call([*compose, "start", "iam-worker"])
    leftover = "unknown"
    for _ in range(45):
        leftover = compose_exec(
            compose,
            "postgres",
            "psql",
            "-U",
            os.environ["POSTGRES_SUPERUSER"],
            "-d",
            os.environ["IAM_DB_NAME"],
            "-tAc",
            "SELECT count(*) FROM iam_outbox WHERE status<>'delivered';",
        ).strip()
        if leftover == "0":
            break
        time.sleep(2)
    if leftover != "0":
        compose_exec(compose, "iam-service", "uv", "run", "python", "-m", "app.cli.outbox_replay")
        for _ in range(30):
            leftover = compose_exec(
                compose,
                "postgres",
                "psql",
                "-U",
                os.environ["POSTGRES_SUPERUSER"],
                "-d",
                os.environ["IAM_DB_NAME"],
                "-tAc",
                "SELECT count(*) FROM iam_outbox WHERE status<>'delivered';",
            ).strip()
            if leftover == "0":
                break
            time.sleep(2)
    expect(leftover == "0", f"A12 leftover {leftover}")
    results.append("A12 ok")

    # A11 IAM down => audit query 503
    live_token = admin.token
    subprocess.check_call([*compose, "stop", "iam-service"])
    audit_api = Api(base)
    audit_api.token = live_token
    down, dbody = audit_api.call("GET", "/api/v1/audit/events")
    expect(down == 503, f"A11 expected 503 got {down} {dbody}")
    subprocess.check_call([*compose, "start", "iam-service"])
    wait_gateway(base)
    results.append("A11 ok")

    # isolation
    try:
        compose_exec(
            compose,
            "postgres",
            "psql",
            "-U",
            os.environ["IAM_DB_USER"],
            "-d",
            os.environ["AUDIT_DB_NAME"],
            "-c",
            "SELECT 1",
        )
        raise Failed("iam user connected to audit db")
    except subprocess.CalledProcessError:
        results.append("isolation iam->audit ok")

    print("\n".join(results))
    print("p6_accept_ok")


if __name__ == "__main__":
    run()

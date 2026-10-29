from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.http_utils import read_named_upload, success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    FileKind,
    PromptBody,
    ReleaseBody,
    RunFileKind,
    SampleRunBody,
    TestRowsBody,
    file_response,
)
from app.api.security import CategoryAccess, SecurityClass, classified, get_category_access, require_ai_permission
from app.application import prompts as service
from app.application import releases, sample_runs, test_rows
from app.application.asking import available_models
from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.code_tables import SYSTEM_CODE_TABLES

router = APIRouter(prefix="/api/v1/ai/prompts", tags=["ai-prompts"])
RESOURCE = "ai.prompts"
RELEASE_RESOURCE = "ai.releases"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_prompts(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(
        {
            "items": await service.list_prompts(session, access),
            "models": await available_models(session),
            "categories": access.options(),
            "code_tables": [{"key": key, "name": name} for key, name in SYSTEM_CODE_TABLES.items()],
        }
    )


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_prompt(
    body: PromptBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(await service.create_prompt(session, actor, access, body.model_dump()), status_code=201)


@router.put("/{prompt_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_prompt(
    prompt_id: str,
    body: PromptBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_prompt(session, actor, access, prompt_id, body.model_dump()))


@router.delete("/{prompt_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "delete")),
) -> JSONResponse:
    await service.delete_prompt(session, actor, access, prompt_id)
    return success_json(None)


@router.post("/{prompt_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def upload_file(
    prompt_id: str,
    kind: FileKind,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    # 鉴权通过后才解析 multipart，并且边读边按上限中止。
    content, filename = await read_named_upload(request, get_settings().upload_max_bytes, missing="请选择要上传的文件")
    return success_json(await service.upload_file(session, actor, access, prompt_id, kind, (filename, content)))


@router.post("/{prompt_id}/test-data")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def save_test_rows(
    prompt_id: str,
    body: TestRowsBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    """从数据库取来的测试数据（前端从政策服务取）存成模板的测试 Excel，替换原来的。"""

    return success_json(await service.save_test_rows(session, actor, access, prompt_id, body.model_dump()))


@router.delete("/{prompt_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_file(
    prompt_id: str,
    kind: FileKind,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.delete_file(session, actor, access, prompt_id, kind))


@router.get("/{prompt_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def download_file(
    prompt_id: str,
    kind: FileKind,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "export")),
) -> Response:
    content, filename = await service.download_file(session, actor, access, prompt_id, kind)
    return file_response(content, filename)


@router.get("/code-preview")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def preview_system_code(
    code_table: str = Query(max_length=32, description="系统码表的键"),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    """系统码表的字数和前几行：选码表时看一眼内容，不用先保存模板。"""

    return success_json(await service.preview_system_code(code_table))


@router.get("/{prompt_id}/code-preview")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def preview_uploaded_code(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    """上传的码表文件的字数和前几行；看内容不算导出，下载整份才要导出权限。"""

    return success_json(await service.preview_uploaded_code(session, access, prompt_id))


@router.get("/{prompt_id}/test-rows")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def test_rows_preview(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    """测试样本前几行，每格只给开头一段和总字数：试发选第几行、发之前先看这一行的数据。"""

    return success_json(await test_rows.preview(session, access, prompt_id))


@router.get("/{prompt_id}/sample-run")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def view_sample_run(
    prompt_id: str,
    run_id: str | None = Query(default=None, max_length=32, description="看哪一次，默认最近一次"),
    compare_id: str | None = Query(default=None, max_length=32, description="和哪一次比，默认前一次；none 不比"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await sample_runs.view(session, access, prompt_id, run_id=run_id, compare_id=compare_id))


@router.post("/{prompt_id}/sample-run")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def start_sample_run(
    prompt_id: str,
    body: SampleRunBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "ask")),
) -> JSONResponse:
    """和试发一样会花钱，要试发的权限。"""

    return success_json(await sample_runs.start(session, actor, access, prompt_id, body.model_dump()), status_code=201)


@router.post("/{prompt_id}/sample-run/stop")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def stop_sample_run(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "ask")),
) -> JSONResponse:
    return success_json(await sample_runs.stop(session, actor, access, prompt_id))


@router.post("/{prompt_id}/sample-run/{run_id}/retry")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def retry_sample_run(
    prompt_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "ask")),
) -> JSONResponse:
    """只重问失败和没跑到的行，会花钱，和试跑同一个权限。"""

    return success_json(await sample_runs.retry(session, actor, access, prompt_id, run_id))


@router.get("/{prompt_id}/sample-run/{run_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def download_sample_run(
    prompt_id: str,
    run_id: str,
    kind: RunFileKind,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "export")),
) -> Response:
    """和模板附件一样要模板的导出档：在模板页试跑的人不用另有批量任务的权限。"""

    content, filename = await sample_runs.download(session, actor, access, prompt_id, run_id, kind)
    return file_response(content, filename)


@router.get("/{prompt_id}/releases")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_releases(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await releases.list_releases(session, access, prompt_id))


@router.post("/{prompt_id}/release")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def publish(
    prompt_id: str,
    body: ReleaseBody | None = None,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RELEASE_RESOURCE, "publish")),
) -> JSONResponse:
    """上线是管理员的事：业务人员能改模板，但不能让改动直接进定时任务。"""

    version = body.version if body else None
    return success_json(await releases.publish(session, actor, access, prompt_id, version=version))


@router.post("/{prompt_id}/offline")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def take_offline(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RELEASE_RESOURCE, "publish")),
) -> JSONResponse:
    return success_json(await releases.take_offline(session, actor, access, prompt_id))

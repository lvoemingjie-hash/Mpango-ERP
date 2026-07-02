"""U4-I-B2 intake apply service/API contract tests."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.test_u4c_intake_api_contract import (
    OTHER_TENANT_ID,
    TEST_TENANT_ID,
    TEST_TENANT_SCHEMA,
    _client_for,
    _ensure_intake_schema,
    _error_code,
)

APPLY_PATH = "/api/v1/intake/workspaces/{workspace_id}/apply"
TEST_USER_ID = "00000000-0000-0000-0000-0000000000aa"


async def _reset_apply_tables(session) -> None:
    await _ensure_intake_schema(session)
    await session.execute(text(f'DELETE FROM "{TEST_TENANT_SCHEMA}".skus'))
    await session.commit()


async def _create_ready_workspace(
    session,
    *,
    tenant_id: str = TEST_TENANT_ID,
    status: str = "READY_FOR_EXPORT",
    apply_status: str = "not_applied",
    rows: list[dict[str, str | None]] | None = None,
    blocking_issue: bool = False,
) -> uuid.UUID:
    workspace_id = uuid.uuid4()
    upload_id = uuid.uuid4()
    staged_rows = rows or [
        {"sku_code": "U4IB2-001", "name": "Apply Alpha", "unit": "piece", "category": "dry"},
        {"sku_code": "U4IB2-002", "name": "Apply Beta", "unit": "case", "category": "fresh"},
    ]

    await session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".intake_workspaces '
            "(id, tenant_id, name, source_type, status, apply_status) "
            "VALUES (:id, :tenant_id, 'Apply workspace', 'CATALOG_REFRESH', :status, :apply_status)"
        ),
        {"id": workspace_id, "tenant_id": tenant_id, "status": status, "apply_status": apply_status},
    )
    await session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".intake_uploads '
            "(id, tenant_id, workspace_id, filename, file_ext, file_size_bytes, sha256, status, "
            "row_count, column_count, headers_raw, headers_normalized) "
            "VALUES (:id, :tenant_id, :workspace_id, 'apply.csv', 'csv', 12, :sha256, 'PARSED', "
            ":row_count, 4, '[\"sku_code\", \"name\", \"unit\", \"category\"]'::jsonb, "
            "'{\"sku_code\": \"sku_code\", \"name\": \"name\", \"unit\": \"unit\", "
            "\"category\": \"category\"}'::jsonb)"
        ),
        {
            "id": upload_id,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "sha256": "0" * 64,
            "row_count": len(staged_rows),
        },
    )

    for index, row in enumerate(staged_rows):
        await session.execute(
            text(
                f'INSERT INTO "{TEST_TENANT_SCHEMA}".intake_product_rows '
                "(id, tenant_id, workspace_id, upload_id, source_row_number, row_index, raw_values, "
                "normalized_values, mapping_version, sku_code, name, unit, category, review_status) "
                "VALUES (:id, :tenant_id, :workspace_id, :upload_id, :source_row_number, :row_index, "
                "'{}'::jsonb, '{}'::jsonb, 2, :sku_code, :name, :unit, :category, 'VALID')"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "upload_id": upload_id,
                "source_row_number": index + 2,
                "row_index": index,
                "sku_code": row.get("sku_code"),
                "name": row.get("name"),
                "unit": row.get("unit"),
                "category": row.get("category"),
            },
        )

    if blocking_issue:
        await session.execute(
            text(
                f'INSERT INTO "{TEST_TENANT_SCHEMA}".intake_validation_issues '
                "(id, tenant_id, workspace_id, severity, code, message, is_blocking) "
                "VALUES (:id, :tenant_id, :workspace_id, 'ERROR', 'BLOCKING_TEST', 'blocked', true)"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_id, "workspace_id": workspace_id},
        )

    await session.commit()
    return workspace_id


async def _sku_codes(session) -> list[str]:
    result = await session.execute(
        text(f'SELECT sku_code FROM "{TEST_TENANT_SCHEMA}".skus ORDER BY sku_code')
    )
    return list(result.scalars().all())


async def _workspace_audit(session, workspace_id: uuid.UUID) -> dict:
    result = await session.execute(
        text(
            f'SELECT apply_status, applied_at, applied_by, apply_result '
            f'FROM "{TEST_TENANT_SCHEMA}".intake_workspaces WHERE id = :workspace_id'
        ),
        {"workspace_id": workspace_id},
    )
    return dict(result.mappings().one())


async def _row_audit(session, workspace_id: uuid.UUID) -> list[dict]:
    result = await session.execute(
        text(
            f'SELECT sku_code, apply_status, target_sku_id, apply_error_code, apply_error_message '
            f'FROM "{TEST_TENANT_SCHEMA}".intake_product_rows '
            "WHERE workspace_id = :workspace_id ORDER BY row_index"
        ),
        {"workspace_id": workspace_id},
    )
    return [dict(row) for row in result.mappings().all()]


@pytest.mark.asyncio
async def test_apply_requires_intake_update(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)

    async with _client_for(permissions=["skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 403
    assert _error_code(response) == "PERMISSION_DENIED"
    assert await _sku_codes(async_session) == []


@pytest.mark.asyncio
async def test_apply_requires_skus_import(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)

    async with _client_for(permissions=["intake:update"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 403
    assert _error_code(response) == "PERMISSION_DENIED"
    assert await _sku_codes(async_session) == []


@pytest.mark.asyncio
async def test_successful_apply_creates_skus_and_updates_audit(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["workspace_id"] == str(workspace_id)
    assert data["apply_status"] == "applied"
    assert data["created_count"] == 2
    assert len(data["created_sku_ids"]) == 2
    assert await _sku_codes(async_session) == ["U4IB2-001", "U4IB2-002"]

    workspace = await _workspace_audit(async_session, workspace_id)
    assert workspace["apply_status"] == "applied"
    assert workspace["applied_at"] is not None
    assert str(workspace["applied_by"]) == TEST_USER_ID
    assert workspace["apply_result"]["created_count"] == 2
    assert workspace["apply_result"]["row_count"] == 2

    rows = await _row_audit(async_session, workspace_id)
    assert [row["apply_status"] for row in rows] == ["applied", "applied"]
    assert all(row["target_sku_id"] for row in rows)
    assert all(row["apply_error_code"] is None for row in rows)


@pytest.mark.asyncio
async def test_duplicate_staged_sku_code_fails_before_any_sku_write(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(
        async_session,
        rows=[
            {"sku_code": "U4IB2-DUP", "name": "One", "unit": "piece", "category": None},
            {"sku_code": "U4IB2-DUP", "name": "Two", "unit": "piece", "category": None},
        ],
    )

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 409
    assert _error_code(response) == "DUPLICATE_STAGED_SKU_CODE"
    assert await _sku_codes(async_session) == []
    assert (await _workspace_audit(async_session, workspace_id))["apply_status"] == "not_applied"


@pytest.mark.asyncio
async def test_existing_official_sku_code_fails_before_any_sku_write(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".skus (sku_code, name, unit, is_active) '
            "VALUES ('U4IB2-001', 'Existing', 'piece', true)"
        )
    )
    await async_session.commit()

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 409
    assert _error_code(response) == "SKU_CODE_EXISTS"
    assert await _sku_codes(async_session) == ["U4IB2-001"]
    assert (await _workspace_audit(async_session, workspace_id))["apply_status"] == "not_applied"


@pytest.mark.asyncio
async def test_blocking_validation_issue_fails_apply(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session, blocking_issue=True)

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 409
    assert _error_code(response) == "BLOCKING_ISSUES"
    assert await _sku_codes(async_session) == []


@pytest.mark.asyncio
async def test_workspace_not_ready_for_export_fails_apply(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session, status="MAPPED")

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 409
    assert _error_code(response) == "WORKSPACE_NOT_READY"
    assert await _sku_codes(async_session) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("apply_status", ["applying", "failed"])
async def test_non_not_applied_status_fails_without_writes_or_audit_changes(async_session, apply_status):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session, apply_status=apply_status)

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 409
    assert _error_code(response) == "INVALID_APPLY_STATUS"
    assert await _sku_codes(async_session) == []
    assert (await _workspace_audit(async_session, workspace_id))["apply_status"] == apply_status
    assert [row["apply_status"] for row in await _row_audit(async_session, workspace_id)] == [
        "not_applied",
        "not_applied",
    ]


@pytest.mark.asyncio
async def test_repeated_apply_returns_already_applied_without_duplicate_skus(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        first = await client.post(APPLY_PATH.format(workspace_id=workspace_id))
        second = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert first.status_code == 200
    assert second.status_code == 409
    assert _error_code(second) == "ALREADY_APPLIED"
    assert await _sku_codes(async_session) == ["U4IB2-001", "U4IB2-002"]


@pytest.mark.asyncio
async def test_mid_apply_failure_rolls_back_sku_writes_and_audit(async_session, monkeypatch):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)

    from api.v1 import intake

    original_create = intake.intake_apply_service._sku_repo.create

    async def _create_then_fail_once(db, *, sku):
        await original_create(db, sku=sku)
        raise RuntimeError("forced mid-apply failure")

    monkeypatch.setattr(intake.intake_apply_service._sku_repo, "create", _create_then_fail_once)

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 500
    assert await _sku_codes(async_session) == []
    assert (await _workspace_audit(async_session, workspace_id))["apply_status"] == "not_applied"
    assert [row["apply_status"] for row in await _row_audit(async_session, workspace_id)] == [
        "not_applied",
        "not_applied",
    ]


@pytest.mark.asyncio
async def test_cannot_apply_another_tenant_workspace(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session, tenant_id=OTHER_TENANT_ID)

    async with _client_for(permissions=["intake:update", "skus:import"], tenant_id=TEST_TENANT_ID) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 404
    assert _error_code(response) == "WORKSPACE_NOT_FOUND"
    assert await _sku_codes(async_session) == []


@pytest.mark.asyncio
async def test_missing_required_row_fields_fails_before_any_sku_write(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(
        async_session,
        rows=[{"sku_code": "U4IB2-MISSING", "name": None, "unit": "piece", "category": None}],
    )

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 422
    assert _error_code(response) == "INCOMPLETE_STAGED_ROWS"
    assert await _sku_codes(async_session) == []

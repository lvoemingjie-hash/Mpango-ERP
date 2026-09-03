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
CONTRACT_MIGRATION = (
    "SUPERSEDED_BY_SKU_R0_M1_CATALOG_AND_INVENTORY_INITIALIZATION_CONTRACT"
)


async def _reset_apply_tables(session) -> None:
    await _ensure_intake_schema(session)
    await session.execute(text(f'DELETE FROM "{TEST_TENANT_SCHEMA}".inventory_stocks'))
    await session.execute(text(f'DELETE FROM "{TEST_TENANT_SCHEMA}".skus'))
    await session.execute(text(f'DELETE FROM "{TEST_TENANT_SCHEMA}".catalog_products'))
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


async def _catalog_stock_state(session) -> dict[str, int]:
    result = await session.execute(
        text(
            f'SELECT '
            f'(SELECT COUNT(*) FROM "{TEST_TENANT_SCHEMA}".catalog_products) AS products, '
            f'(SELECT COUNT(*) FROM "{TEST_TENANT_SCHEMA}".skus) AS units, '
            f'(SELECT COUNT(*) FROM "{TEST_TENANT_SCHEMA}".inventory_stocks) AS stocks, '
            f'(SELECT COUNT(*) FROM "{TEST_TENANT_SCHEMA}".skus s '
            f' LEFT JOIN "{TEST_TENANT_SCHEMA}".catalog_products p ON p.id = s.catalog_product_id '
            f' WHERE p.id IS NULL) AS orphan_units, '
            f'(SELECT COUNT(*) FROM "{TEST_TENANT_SCHEMA}".inventory_stocks i '
            f' WHERE i.quantity_on_hand <> 0 OR i.quantity_reserved <> 0) AS nonzero_stocks'
        )
    )
    return dict(result.mappings().one())


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
    assert await _catalog_stock_state(async_session) == {
        "products": 0, "units": 0, "stocks": 0,
        "orphan_units": 0, "nonzero_stocks": 0,
    }


@pytest.mark.asyncio
async def test_apply_requires_skus_import(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)

    async with _client_for(permissions=["intake:update"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 403
    assert _error_code(response) == "PERMISSION_DENIED"
    assert await _sku_codes(async_session) == []
    assert await _catalog_stock_state(async_session) == {
        "products": 0, "units": 0, "stocks": 0,
        "orphan_units": 0, "nonzero_stocks": 0,
    }


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
    assert await _catalog_stock_state(async_session) == {
        "products": 2, "units": 2, "stocks": 2,
        "orphan_units": 0, "nonzero_stocks": 0,
    }

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
    product_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".catalog_products (id, name, is_active) '
            "VALUES (:product_id, 'Existing', true)"
        ),
        {"product_id": product_id},
    )
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".skus '
            "(id, catalog_product_id, sku_code, name, unit, is_active) "
            "VALUES (:sku_id, :product_id, 'U4IB2-001', 'Existing', 'piece', true)"
        ),
        {"sku_id": sku_id, "product_id": product_id},
    )
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".inventory_stocks '
            "(id, sku_id, quantity_on_hand, quantity_reserved) "
            "VALUES (:stock_id, :sku_id, 0, 0)"
        ),
        {"stock_id": uuid.uuid4(), "sku_id": sku_id},
    )
    await async_session.commit()

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 409
    assert _error_code(response) == "SKU_CODE_EXISTS"
    assert await _sku_codes(async_session) == ["U4IB2-001"]
    assert await _catalog_stock_state(async_session) == {
        "products": 1, "units": 1, "stocks": 1,
        "orphan_units": 0, "nonzero_stocks": 0,
    }
    assert (await _workspace_audit(async_session, workspace_id))["apply_status"] == "not_applied"


@pytest.mark.asyncio
async def test_soft_deleted_sku_code_remains_reserved(async_session):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(
        async_session,
        rows=[{"sku_code": "U4IB2-RETIRED", "name": "Replacement", "unit": "piece", "category": None}],
    )
    product_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".catalog_products (id, name, is_active) '
            "VALUES (:product_id, 'Retired', true)"
        ),
        {"product_id": product_id},
    )
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".skus '
            "(id, catalog_product_id, sku_code, name, unit, is_active, is_deleted) "
            "VALUES (:sku_id, :product_id, 'U4IB2-RETIRED', 'Retired', 'piece', false, true)"
        ),
        {"sku_id": sku_id, "product_id": product_id},
    )
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".inventory_stocks '
            "(id, sku_id, quantity_on_hand, quantity_reserved) VALUES (:stock_id, :sku_id, 0, 0)"
        ),
        {"stock_id": uuid.uuid4(), "sku_id": sku_id},
    )
    await async_session.commit()

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 409
    assert _error_code(response) == "SKU_CODE_EXISTS"
    assert await _catalog_stock_state(async_session) == {
        "products": 1, "units": 1, "stocks": 1,
        "orphan_units": 0, "nonzero_stocks": 0,
    }


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
    assert await _catalog_stock_state(async_session) == {
        "products": 2, "units": 2, "stocks": 2,
        "orphan_units": 0, "nonzero_stocks": 0,
    }


@pytest.mark.asyncio
async def test_mid_apply_failure_rolls_back_sku_writes_and_audit(async_session, monkeypatch):
    await _reset_apply_tables(async_session)
    workspace_id = await _create_ready_workspace(async_session)

    from api.v1 import intake
    from services import intake_apply_service as intake_apply_module
    from services.sku_integrity import flush_skus_or_409 as real_guard

    async def _flush_then_fail_once(db, *, sku_code):
        await real_guard(db, sku_code=sku_code)
        raise RuntimeError("forced mid-apply failure")

    monkeypatch.setattr(intake_apply_module, "flush_skus_or_409", _flush_then_fail_once)

    async with _client_for(permissions=["intake:update", "skus:import"]) as client:
        response = await client.post(APPLY_PATH.format(workspace_id=workspace_id))

    assert response.status_code == 500
    assert await _sku_codes(async_session) == []
    assert await _catalog_stock_state(async_session) == {
        "products": 0, "units": 0, "stocks": 0,
        "orphan_units": 0, "nonzero_stocks": 0,
    }
    assert (await _workspace_audit(async_session, workspace_id))["apply_status"] == "not_applied"
    assert [row["apply_status"] for row in await _row_audit(async_session, workspace_id)] == [
        "not_applied",
        "not_applied",
    ]


@pytest.mark.asyncio
async def test_concurrent_intake_apply_sku_code_races_deterministically(async_session, monkeypatch):
    """R5-F2 P2-01 — deterministic real-PG two-session intake SKU race.

    Two independent sessions/connections apply two ready workspaces of the
    same tenant carrying the SAME new SKU code. Both friendly existing-code
    prechecks pass; both executions synchronize on a wrapper around the
    imported ``flush_skus_or_409`` immediately before the real shared guarded
    flush, and the wrapper delegates to the real guard unchanged.

    Deterministic outcome per race:
      - exactly one success and exactly one 409 with detail code SKU_EXISTS
      - zero raw IntegrityError / 500 leakage
      - exactly one product, one SKU and one zero-quantity stock row
      - no orphan or duplicate stock rows
      - the losing workspace/audit mutations roll back whole
      - the losing session is immediately reusable
    Both scheduling orders run with repeated deterministic cases; no sleeps.
    """
    import asyncio

    from database.session import AsyncSessionLocal
    from fastapi import HTTPException
    from services import intake_apply_service as intake_apply_module
    from services.intake_apply_service import IntakeApplyService
    from sqlalchemy.exc import IntegrityError
    from services.sku_integrity import flush_skus_or_409 as real_guard

    service = IntakeApplyService()
    orders = (("workspace_a", "workspace_b"), ("workspace_b", "workspace_a"))
    iterations_per_order = 3
    loser_session_by_label: dict[str, object] = {}

    for order in orders:
        for iteration in range(iterations_per_order):
            await _reset_apply_tables(async_session)
            code = f"R5F2RACE-{iteration:02d}"
            ids = {
                "workspace_a": await _create_ready_workspace(
                    async_session,
                    rows=[{"sku_code": code, "name": "Intake Race Alpha", "unit": "piece", "category": "dry"}],
                ),
                "workspace_b": await _create_ready_workspace(
                    async_session,
                    rows=[{"sku_code": code, "name": "Intake Race Beta", "unit": "piece", "category": "dry"}],
                ),
            }

            # Synchronization point: both executions park here AFTER their
            # friendly existing-code prechecks and release together into the
            # real guarded flush, which is delegated to UNCHANGED.
            arrivals = {"count": 0}
            gate = asyncio.Event()

            async def barred_flush(db, *, sku_code):
                arrivals["count"] += 1
                if arrivals["count"] == 1:
                    await gate.wait()
                else:
                    gate.set()
                return await real_guard(db, sku_code=sku_code)

            monkeypatch.setattr(intake_apply_module, "flush_skus_or_409", barred_flush)

            outcomes: dict[str, tuple[str, object]] = {}
            integrity_leaks: list[IntegrityError] = []

            async def run_apply(label: str, session) -> None:
                try:
                    await service.apply_workspace(
                        session,
                        tenant_id=uuid.UUID(TEST_TENANT_ID),
                        workspace_id=ids[label],
                        user_id=uuid.UUID(TEST_USER_ID),
                    )
                    await session.commit()
                    outcomes[label] = ("success", None)
                except HTTPException as exc:
                    await session.rollback()
                    outcomes[label] = ("sku_exists_409", exc)
                    loser_session_by_label[label] = session
                except IntegrityError as exc:  # must never happen
                    await session.rollback()
                    outcomes[label] = ("integrity_error", exc)
                    integrity_leaks.append(exc)

            sessions = {label: AsyncSessionLocal() for label in ids}
            try:
                for session in sessions.values():
                    session.info["tenant_schema"] = TEST_TENANT_SCHEMA
                    session.info["tenant_id"] = TEST_TENANT_ID
                    await session.execute(
                        text(f'SET search_path TO "{TEST_TENANT_SCHEMA}", public')
                    )

                tasks = [
                    asyncio.create_task(run_apply(order[0], sessions[order[0]])),
                    asyncio.create_task(run_apply(order[1], sessions[order[1]])),
                ]
                await asyncio.gather(*tasks)

                assert sorted(outcome for outcome, _ in outcomes.values()) == [
                    "sku_exists_409",
                    "success",
                ], f"order={order} iteration={iteration}: outcomes {outcomes}"
                assert not integrity_leaks, f"raw IntegrityError leaked: {integrity_leaks}"

                loser_label = next(
                    label for label, (outcome, _) in outcomes.items() if outcome == "sku_exists_409"
                )
                exc = outcomes[loser_label][1]
                assert exc.status_code == 409, f"expected 409, got {exc.status_code}"
                assert isinstance(exc.detail, dict) and exc.detail.get("code") == "SKU_EXISTS", exc.detail

                # Exactly one product, one SKU and one zero-quantity stock row
                # for the raced code; no orphan or duplicate stock anywhere.
                state = await _catalog_stock_state(async_session)
                assert state == {
                    "products": 1, "units": 1, "stocks": 1,
                    "orphan_units": 0, "nonzero_stocks": 0,
                }, f"order={order} iteration={iteration}: {state}"
                quantities = (
                    await async_session.execute(
                        text(
                            f'SELECT i.quantity_on_hand FROM "{TEST_TENANT_SCHEMA}".inventory_stocks i '
                            f'JOIN "{TEST_TENANT_SCHEMA}".skus s ON s.id = i.sku_id '
                            "WHERE s.sku_code = :code"
                        ),
                        {"code": code},
                    )
                ).scalars().all()
                assert quantities == [0], (
                    f"expected exactly one zero-quantity stock row, got {quantities}"
                )

                # The winner is applied; the loser rolled back whole.
                winner_label = next(label for label in ids if label != loser_label)
                winner_audit = await _workspace_audit(async_session, ids[winner_label])
                assert winner_audit["apply_status"] == "applied"
                assert [
                    row["apply_status"] for row in await _row_audit(async_session, ids[winner_label])
                ] == ["applied"]
                loser_audit = await _workspace_audit(async_session, ids[loser_label])
                assert loser_audit["apply_status"] == "not_applied"
                assert loser_audit["applied_at"] is None
                loser_rows = await _row_audit(async_session, ids[loser_label])
                assert [row["apply_status"] for row in loser_rows] == ["not_applied"]
                assert all(row["target_sku_id"] is None for row in loser_rows)

                # The losing session is immediately reusable: a real query
                # works on the very session that took the 409 (it is closed
                # only afterwards, so no transaction leaks past the test).
                loser_session = loser_session_by_label[loser_label]
                reused = (
                    await loser_session.execute(
                        text(
                            f'SELECT apply_status FROM "{TEST_TENANT_SCHEMA}".intake_workspaces '
                            "WHERE id = :workspace_id"
                        ),
                        {"workspace_id": ids[loser_label]},
                    )
                ).scalar_one()
                assert reused == "not_applied", (
                    "loser session must be immediately reusable after the 409"
                )
            finally:
                for session in sessions.values():
                    await session.close()


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

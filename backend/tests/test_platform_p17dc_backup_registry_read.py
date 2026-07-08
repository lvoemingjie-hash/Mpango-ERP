"""P17-D-C unit tests: backup / status source registry READ wiring.

Covers the P17-D-B test plan (section 11, G1-G18) cases that are exercisable
without a live database -- the durable-source builder, the best-effort loader's
resolution + degrade-on-failure + read-only behavior, the registry assembly
through the route, and the no-P22-wiring invariant. The closed-vocabulary DB
CHECK (G14) and the SQL-level filtering / in_progress exclusion (G17) are
covered by the ephemeral-DB migration test (test_platform_p17dc_backup_migration).

Mapping (unit-testable):
  G1  fresh success renders success               -> test_fresh_success_renders_success_available
  G2  stale success downgrades to stale           -> test_stale_success_downgrades_to_stale
  G3  no outcome -> unknown/null, never healthy   -> test_*_no_outcome* / test_returns_none_when_not_available
  G5  failed outcome + allowlisted reason         -> test_failed_outcome_renders_failed_allowlisted_reason
  G6  raw failure reason redacted to unknown      -> test_raw_failure_reason_redacted_to_unknown
  G7  restore-test freshness (passed / stale)     -> test_restore_test_passed_within_cadence / _stale_beyond_cadence
  G8  restore-test unknown until a runner exists  -> test_no_restore_test_row_yields_null_status
  G9  success requires fresh + available          -> test_success_requires_fresh_and_available
  G12 read failure degrades, no 500               -> test_read_failure_returns_none / *_at_registry
  G13 tenant-specific preferred over platform     -> test_tenant_specific_preferred* / test_platform_wide_fallback
  G15 no P22 wiring                               -> test_p22_backup_check_still_not_implemented
  G16 read path is read-only                      -> test_load_map_performs_no_mutations
  null!=0 / derived fields                        -> test_export_available_* / test_retention_policy_from_policy_row
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")

from api.v1.platform.p17.services import (  # noqa: E402
    _BACKUP_UNAVAILABLE_REASON,
    _BACKUP_UNKNOWN_REASON,
    _BackupSourceRead,
    _build_backup_status,
    _load_backup_status_map,
)

pytestmark = pytest.mark.unit

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
P17_BASE = "/api/v1/platform/p17"
REGISTRY_PATH = f"{P17_BASE}/registry"
TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
TID_UUID = UUID(TENANT_ID)

NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)

_ACTIVE_PATCHERS: list = []


def _start_patch(target, new):
    p = patch(target, new=new)
    p.start()
    _ACTIVE_PATCHERS.append(p)
    return p


@pytest.fixture(autouse=True)
def _stop_patches_after_test():
    yield
    while _ACTIVE_PATCHERS:
        _ACTIVE_PATCHERS.pop().stop()


# ---------------------------------------------------------------------------
# Row builders (stand-ins for ORM rows; only the attributes the read path reads).
# ---------------------------------------------------------------------------


def _outcome(
    *,
    tenant_id=None,
    job_kind="backup_job",
    status="success",
    completed_at=None,
    bytes_written=100,
    failure_reason_code=None,
    started_at=None,
):
    o = MagicMock()
    o.tenant_id = tenant_id
    o.job_kind = job_kind
    o.status = status
    o.completed_at = completed_at
    o.started_at = started_at or completed_at
    o.bytes_written = bytes_written
    o.failure_reason_code = failure_reason_code
    o.source_writer_id = "backup_postgres.sh"
    return o


def _policy(
    *,
    tenant_id=None,
    retention_policy=None,
    export_enabled=None,
    restore_test_cadence_hours=None,
):
    p = MagicMock()
    p.tenant_id = tenant_id
    p.retention_policy = retention_policy
    p.export_enabled = export_enabled
    p.restore_test_cadence_hours = restore_test_cadence_hours
    return p


def _read_available(*, backup_row=None, restore_row=None, policy_row=None):
    return _BackupSourceRead(
        source_status="available",
        backup_row=backup_row,
        restore_row=restore_row,
        policy_row=policy_row,
    )


# ===========================================================================
# _build_backup_status (pure builder; G1, G2, G5, G6, G7, G8, G9, derived)
# ===========================================================================


class TestBuildBackupStatus:
    def test_fresh_success_renders_success_available(self):
        row = _outcome(
            status="success", completed_at=NOW - timedelta(hours=2), bytes_written=2048
        )
        bs = _build_backup_status(_read_available(backup_row=row), NOW)
        assert bs is not None
        assert bs.last_backup_status == "success"
        assert bs.backup_source_status == "available"
        assert bs.last_backup_at == NOW - timedelta(hours=2)
        assert bs.export_available is True
        assert bs.last_status_check_at == NOW

    def test_stale_success_downgrades_to_stale(self):
        row = _outcome(status="success", completed_at=NOW - timedelta(hours=48))
        bs = _build_backup_status(_read_available(backup_row=row), NOW)
        assert bs is not None
        assert bs.last_backup_status == "stale"
        assert bs.last_backup_status != "success"

    def test_failed_outcome_renders_failed_allowlisted_reason(self):
        row = _outcome(
            status="failed",
            completed_at=NOW - timedelta(hours=1),
            bytes_written=None,
            failure_reason_code="backup_incomplete",
        )
        bs = _build_backup_status(_read_available(backup_row=row), NOW)
        assert bs is not None
        assert bs.last_backup_status == "failed"
        assert bs.failure_reason_redacted == "backup_incomplete"
        assert bs.export_available is False

    def test_raw_failure_reason_redacted_to_unknown(self):
        # A writer that tried to persist a raw stack trace is collapsed by
        # redact_failure_reason to 'unknown' before the response is built; the
        # raw secret never reaches failure_reason_redacted.
        raw = "Traceback (most recent call last): OperationalError at host:5432"
        row = _outcome(
            status="failed",
            completed_at=NOW - timedelta(hours=1),
            bytes_written=None,
            failure_reason_code=raw,
        )
        bs = _build_backup_status(_read_available(backup_row=row), NOW)
        assert bs is not None
        assert bs.failure_reason_redacted == "unknown"
        assert bs.failure_reason_redacted != raw
        assert "Traceback" not in (bs.failure_reason_redacted or "")

    def test_restore_test_passed_within_cadence(self):
        restore = _outcome(
            job_kind="restore_test_job",
            status="success",
            completed_at=NOW - timedelta(hours=24),
        )
        bs = _build_backup_status(_read_available(restore_row=restore), NOW)
        # No backup_job outcome -> only restore applies; still 'available'.
        assert bs is not None
        assert bs.backup_source_status == "available"
        assert bs.restore_test_status == "passed"
        assert bs.last_restore_test_at == NOW - timedelta(hours=24)

    def test_restore_test_stale_beyond_cadence(self):
        restore = _outcome(
            job_kind="restore_test_job",
            status="success",
            completed_at=NOW - timedelta(hours=200),  # > 168h default cadence
        )
        bs = _build_backup_status(_read_available(restore_row=restore), NOW)
        assert bs is not None
        assert bs.restore_test_status == "stale"

    def test_restore_test_failed_verdict(self):
        restore = _outcome(
            job_kind="restore_test_job",
            status="failed",
            completed_at=NOW - timedelta(hours=12),
            failure_reason_code="restore_test_failed",
        )
        bs = _build_backup_status(_read_available(restore_row=restore), NOW)
        assert bs is not None
        assert bs.restore_test_status == "failed"

    def test_no_restore_test_row_yields_null_status(self):
        # No restore_test_job outcome recorded -> restore_test_status null (the
        # expected state until a restore-test runner exists).
        row = _outcome(status="success", completed_at=NOW - timedelta(hours=1))
        bs = _build_backup_status(_read_available(backup_row=row), NOW)
        assert bs is not None
        assert bs.restore_test_status is None
        assert bs.last_restore_test_at is None

    def test_per_policy_restore_test_cadence_override(self):
        # Default cadence (168h) would keep a 48h-old test 'passed'; a policy
        # override of 24h downgrades it to 'stale'.
        restore = _outcome(
            job_kind="restore_test_job",
            status="success",
            completed_at=NOW - timedelta(hours=48),
        )
        pol = _policy(restore_test_cadence_hours=24)
        bs = _build_backup_status(
            _read_available(restore_row=restore, policy_row=pol), NOW
        )
        assert bs is not None
        assert bs.restore_test_status == "stale"

    def test_export_available_false_when_latest_backup_failed(self):
        row = _outcome(
            status="failed",
            completed_at=NOW - timedelta(hours=1),
            failure_reason_code="backup_incomplete",
        )
        bs = _build_backup_status(_read_available(backup_row=row), NOW)
        assert bs is not None
        assert bs.export_available is False

    def test_retention_policy_from_policy_row(self):
        row = _outcome(status="success", completed_at=NOW - timedelta(hours=1))
        pol = _policy(retention_policy="7 daily", export_enabled=True)
        bs = _build_backup_status(
            _read_available(backup_row=row, policy_row=pol), NOW
        )
        assert bs is not None
        assert bs.retention_policy == "7 daily"

    def test_success_requires_fresh_and_available(self):
        # The schema backstop rejects success without an available source; the
        # builder always sets available when it builds, and routes through
        # enforce_backup_freshness, so a null-timestamp success cannot survive.
        from api.v1.platform.p17.schemas import TenantBackupStatus

        with pytest.raises(Exception):
            TenantBackupStatus(
                last_backup_status="success",
                last_backup_at=None,
                backup_source_status="available",
            )

    def test_returns_none_when_not_available(self):
        # Unknown read (no outcome) -> None; unavailable read (None) -> None.
        assert _build_backup_status(None, NOW) is None
        assert (
            _build_backup_status(
                _BackupSourceRead(source_status="unknown", reason=_BACKUP_UNKNOWN_REASON),
                NOW,
            )
            is None
        )


# ===========================================================================
# _load_backup_status_map (loader: G3, G12, G13, G16, latest-completed)
# ===========================================================================


def _mock_db_with(outcomes, policies):
    db = MagicMock()
    o1 = MagicMock()
    o1.scalars.return_value.all.return_value = outcomes
    o2 = MagicMock()
    o2.scalars.return_value.all.return_value = policies
    db.execute = AsyncMock(side_effect=[o1, o2])
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.delete = MagicMock()
    return db


class TestLoadBackupStatusMap:
    @pytest.mark.asyncio
    async def test_empty_tenant_ids(self):
        db = _mock_db_with([], [])
        result = await _load_backup_status_map(db, [], NOW)
        assert result == {}
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_failure_returns_none(self):
        # A DB read error -> None (unavailable for all), never raises.
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("backup table unreachable"))
        result = await _load_backup_status_map(db, [TENANT_ID], NOW)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_outcomes_yields_unknown_per_tenant(self):
        db = _mock_db_with([], [])
        result = await _load_backup_status_map(db, [TENANT_ID], NOW)
        assert result is not None
        read = result[TENANT_ID]
        assert read.source_status == "unknown"
        assert read.reason == _BACKUP_UNKNOWN_REASON
        assert read.backup_row is None

    @pytest.mark.asyncio
    async def test_tenant_specific_preferred_over_platform_wide(self):
        tenant_row = _outcome(
            tenant_id=TID_UUID,
            job_kind="backup_job",
            status="success",
            completed_at=NOW - timedelta(hours=10),
        )
        plat_row = _outcome(
            tenant_id=None,
            job_kind="backup_job",
            status="success",
            completed_at=NOW - timedelta(hours=1),  # newer, but platform-wide
        )
        db = _mock_db_with([tenant_row, plat_row], [])
        result = await _load_backup_status_map(db, [TENANT_ID], NOW)
        read = result[TENANT_ID]
        assert read.source_status == "available"
        assert read.backup_row is tenant_row
        assert read.backup_row.completed_at == NOW - timedelta(hours=10)

    @pytest.mark.asyncio
    async def test_platform_wide_fallback_when_no_tenant_outcome(self):
        plat_row = _outcome(
            tenant_id=None,
            job_kind="backup_job",
            status="success",
            completed_at=NOW - timedelta(hours=2),
        )
        db = _mock_db_with([plat_row], [])
        result = await _load_backup_status_map(db, [TENANT_ID], NOW)
        read = result[TENANT_ID]
        assert read.source_status == "available"
        assert read.backup_row is plat_row

    @pytest.mark.asyncio
    async def test_latest_completed_chosen_per_kind(self):
        older = _outcome(
            tenant_id=TID_UUID,
            job_kind="backup_job",
            status="success",
            completed_at=NOW - timedelta(hours=48),
        )
        newer = _outcome(
            tenant_id=TID_UUID,
            job_kind="backup_job",
            status="success",
            completed_at=NOW - timedelta(hours=1),
        )
        db = _mock_db_with([older, newer], [])
        result = await _load_backup_status_map(db, [TENANT_ID], NOW)
        assert result[TENANT_ID].backup_row is newer

    @pytest.mark.asyncio
    async def test_policy_tenant_then_platform_default(self):
        tenant_pol = _policy(tenant_id=TID_UUID, retention_policy="14 daily")
        plat_pol = _policy(tenant_id=None, retention_policy="7 daily")
        row = _outcome(
            tenant_id=TID_UUID, status="success", completed_at=NOW - timedelta(hours=1)
        )
        db = _mock_db_with([row], [tenant_pol, plat_pol])
        result = await _load_backup_status_map(db, [TENANT_ID], NOW)
        assert result[TENANT_ID].policy_row is tenant_pol

    @pytest.mark.asyncio
    async def test_load_map_performs_no_mutations(self):
        # G16: the read path is read-only -- no add / commit / flush / delete.
        row = _outcome(
            tenant_id=TID_UUID, status="success", completed_at=NOW - timedelta(hours=1)
        )
        db = _mock_db_with([row], [])
        await _load_backup_status_map(db, [TENANT_ID], NOW)
        db.add.assert_not_called()
        db.commit.assert_not_called()
        db.flush.assert_not_called()
        db.delete.assert_not_called()


# ===========================================================================
# Registry assembly through the route (G1, G3, G12, G13 at the HTTP level)
# ===========================================================================


def _summary():
    s = MagicMock()
    s.tenant_id = TENANT_ID
    s.tenant_name = "Acme"
    s.tenant_schema = "t_acme"
    s.tier = None
    s.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    s.status = "active"
    s.support_mode_active = False
    return s


def _summary_list(items):
    lst = MagicMock()
    lst.items = items
    lst.total = len(items)
    lst.limit = 50
    lst.offset = 0
    return lst


def _mock_db():
    db = MagicMock()
    ok = MagicMock()
    ok.scalar_one_or_none.return_value = None
    ok.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=ok)
    return db


def _app_with_backup_map(backup_map):
    from api.v1.platform.p17.routes import router
    from api.dependencies import get_db, get_platform_db

    app = FastAPI()

    async def override():
        yield _mock_db()

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.include_router(router)
    _start_patch(
        "api.v1.platform.p17.services.list_tenant_summaries",
        AsyncMock(return_value=_summary_list([_summary()])),
    )
    _start_patch(
        "api.v1.platform.p17.services._load_provisioning_map",
        AsyncMock(return_value={}),
    )
    _start_patch(
        "api.v1.platform.p17.services._load_backup_status_map",
        AsyncMock(return_value=backup_map),
    )
    return app


class TestRegistryAssembly:
    def test_fresh_success_attached_to_registry(self):
        row = _outcome(
            status="success", completed_at=NOW - timedelta(hours=2), bytes_written=2048
        )
        backup_map = {TENANT_ID: _read_available(backup_row=row)}
        client = TestClient(_app_with_backup_map(backup_map))
        # The route computes its own now(); a 2h-old success is fresh under 24h.
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        item = d["items"][0]
        assert item["backup_status"] is not None
        assert item["backup_status"]["last_backup_status"] == "success"
        assert item["backup_status"]["backup_source_status"] == "available"

    def test_no_outcome_backup_null_with_unknown_reason(self):
        backup_map = {
            TENANT_ID: _BackupSourceRead(
                source_status="unknown", reason=_BACKUP_UNKNOWN_REASON
            )
        }
        client = TestClient(_app_with_backup_map(backup_map))
        item = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()["items"][0]
        assert item["backup_status"] is None
        reason = item["unavailable_reason"].lower()
        assert "backup" in reason
        # never a fabricated healthy value
        assert item["backup_status"] != "success"

    def test_read_failure_backup_null_with_unavailable_reason_no_500(self):
        backup_map = None  # _load_backup_status_map returned None (read failed)
        client = TestClient(_app_with_backup_map(backup_map))
        r = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200  # graceful, never 500
        item = r.json()["items"][0]
        assert item["backup_status"] is None
        assert "backup" in item["unavailable_reason"].lower()

    def test_tenant_specific_wins_over_platform_at_registry(self):
        # The tenant-specific outcome is the one rendered at the registry (the
        # loader's tenant-preference resolution is covered in TestLoadBackupStatusMap;
        # here we confirm a tenant backup row flows through to the response).
        tenant_row = _outcome(
            tenant_id=TID_UUID,
            status="success",
            completed_at=NOW - timedelta(hours=10),
            bytes_written=512,
        )
        backup_map = {TENANT_ID: _read_available(backup_row=tenant_row)}
        client = TestClient(_app_with_backup_map(backup_map))
        item = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()["items"][0]
        bs = item["backup_status"]
        assert bs is not None
        assert bs["last_backup_status"] == "success"
        assert bs["last_backup_at"] is not None


# ===========================================================================
# G15: no P22 wiring -- backup.check stays not_implemented / source_unknown
# ===========================================================================


class TestNoP22Wiring:
    def test_p22_backup_check_still_not_implemented(self):
        from api.v1.platform.p22.adapters import (
            _BACKUP_SOURCE_NOT_WIRED,
            _build_descriptor,
            _source_status_for,
        )

        # The P22 backup.check slot is unchanged by P17-D-C: still source_unknown
        # / not_implemented (P22-E3 is the separately gated phase that may bind
        # it to this PROVEN, MERGED, TESTED source behind the seam).
        status, reason = _source_status_for("backup.check")
        assert status == "unknown"
        assert reason == _BACKUP_SOURCE_NOT_WIRED
        desc = _build_descriptor("backup.check")
        assert desc.adapter_result == "not_implemented"
        assert desc.source_status == "unknown"
        assert desc.realizes_execution is False

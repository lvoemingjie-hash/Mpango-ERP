"""
S7-4-T3: DbAssetResolver, Pydantic Schemas & Row-to-Asset Mapping Tests.

Test Categories:
    1. _extract_report_id — URN parsing for report UUIDs
    2. _row_to_asset — SysReport row → BIAsset mapping
    3. Pydantic Schemas — CreateReportRequest, ReportConfig validation
    4. DbAssetResolver — resolve() with mocked DB session
    5. Cache invalidation integration — CRUD → invalidate flow
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from core.governance.db_resolver import (
    DbAssetResolver,
    _extract_report_id,
    _row_to_asset,
)
from core.governance.models import (
    BIAction,
    BIAsset,
    BIDomain,
    DataFreshness,
    ResourceType,
)
from core.governance.registry import (
    invalidate_all,
    invalidate_asset,
    dynamic_cache_size,
    _cache_put,
    _cache_get,
)
from api.schemas.report import (
    CreateReportRequest,
    UpdateReportRequest,
)
from core.bi.report_config import (
    ReportConfig,
    Widget,
    WidgetType,
    ChartType,
    GridPosition,
    DataSource,
    VisualizationOptions,
)
from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
)


# ============================================================================
# Helpers
# ============================================================================

def _valid_widget(wid: str = "w1", wtype: WidgetType = WidgetType.CHART) -> Widget:
    """Create a minimal valid Widget for tests."""
    ds = DataSource(view=ViewScope.SALES_DAILY, metrics=[ReportMetric.REVENUE])
    viz = VisualizationOptions(chart_type=ChartType.BAR) if wtype == WidgetType.CHART else VisualizationOptions()
    return Widget(
        id=wid, type=wtype, title="Test Widget",
        position=GridPosition(x=0, y=0, w=6, h=2),
        data_source=ds, visualization=viz,
    )


def _valid_config(**overrides) -> ReportConfig:
    """Create a minimal valid ReportConfig for tests."""
    defaults = {"widgets": [_valid_widget()]}
    defaults.update(overrides)
    return ReportConfig(**defaults)


def _make_report_row(
    report_id: Optional[uuid.UUID] = None,
    title: str = "My Custom Report",
    description: str = "A test report",
    domain: str = "sales",
    config: Optional[dict] = None,
    owner_id: Optional[uuid.UUID] = None,
    acl: Optional[list] = None,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    is_deleted: bool = False,
):
    """Create a mock SysReport-like object for testing _row_to_asset."""
    row = SimpleNamespace()
    row.id = report_id or uuid.uuid4()
    row.title = title
    row.description = description
    row.domain = domain
    row.config = config or {"layout": "grid", "widgets": [{"type": "chart"}]}
    row.owner_id = owner_id or uuid.uuid4()
    row.acl = acl or []
    row.created_at = created_at or datetime.now(timezone.utc)
    row.updated_at = updated_at or datetime.now(timezone.utc)
    row.is_deleted = is_deleted
    return row


# ============================================================================
# 1. _extract_report_id — URN parsing
# ============================================================================

class TestExtractReportId:
    """Test URN parsing for report UUIDs."""

    def test_valid_report_urn(self):
        """Valid report URN extracts UUID."""
        rid = uuid.uuid4()
        result = _extract_report_id(f"urn:bi:report:sales:{rid}")
        assert result == rid

    def test_valid_report_urn_custom_domain(self):
        """Report URN with custom domain works."""
        rid = uuid.uuid4()
        result = _extract_report_id(f"urn:bi:report:custom:{rid}")
        assert result == rid

    def test_non_report_urn_returns_none(self):
        """Non-report URN (e.g., view) returns None."""
        result = _extract_report_id("urn:bi:view:sales:mv_sales_daily")
        assert result is None

    def test_invalid_uuid_returns_none(self):
        """Report URN with non-UUID identifier returns None."""
        result = _extract_report_id("urn:bi:report:sales:not_a_uuid")
        assert result is None

    def test_wrong_segment_count_returns_none(self):
        """URN with wrong number of segments returns None."""
        result = _extract_report_id("urn:bi:report:sales")
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        result = _extract_report_id("")
        assert result is None

    def test_wrong_prefix_returns_none(self):
        """URN with wrong prefix returns None."""
        rid = uuid.uuid4()
        result = _extract_report_id(f"xxx:bi:report:sales:{rid}")
        assert result is None


# ============================================================================
# 2. _row_to_asset — SysReport row → BIAsset mapping
# ============================================================================

class TestRowToAsset:
    """Test the critical DB row → BIAsset mapping function."""

    def test_basic_mapping(self):
        """Row maps to BIAsset with correct fields."""
        rid = uuid.uuid4()
        owner = uuid.uuid4()
        row = _make_report_row(
            report_id=rid,
            title="Revenue Dashboard",
            description="Monthly revenue",
            domain="sales",
            owner_id=owner,
            acl=["user:abc-123", "role:finance"],
        )
        asset = _row_to_asset(row, tenant_id="tenant-abc")

        assert isinstance(asset, BIAsset)
        assert asset.display_name == "Revenue Dashboard"
        assert asset.description == "Monthly revenue"
        assert asset.tenant_id == "tenant-abc"
        assert asset.owner_id == str(owner)
        assert asset.acl == ["user:abc-123", "role:finance"]
        assert asset.source_phase == "S7-4"
        assert asset.freshness == DataFreshness.SNAPSHOT

    def test_urn_format(self):
        """URN is correctly generated as urn:bi:report:<domain>:<id>."""
        rid = uuid.uuid4()
        row = _make_report_row(report_id=rid, domain="finance")
        asset = _row_to_asset(row, tenant_id="tenant-abc")

        assert asset.urn.resource_type == ResourceType.REPORT
        assert asset.urn.domain == BIDomain.FINANCE
        assert asset.urn.identifier == str(rid)
        assert asset.urn_string == f"urn:bi:report:finance:{rid}"

    def test_domain_mapping_sales(self):
        """Domain 'sales' maps to BIDomain.SALES."""
        row = _make_report_row(domain="sales")
        asset = _row_to_asset(row, tenant_id="t")
        assert asset.urn.domain == BIDomain.SALES

    def test_domain_mapping_finance(self):
        """Domain 'finance' maps to BIDomain.FINANCE."""
        row = _make_report_row(domain="finance")
        asset = _row_to_asset(row, tenant_id="t")
        assert asset.urn.domain == BIDomain.FINANCE

    def test_domain_mapping_executive(self):
        """Domain 'executive' maps to BIDomain.EXECUTIVE."""
        row = _make_report_row(domain="executive")
        asset = _row_to_asset(row, tenant_id="t")
        assert asset.urn.domain == BIDomain.EXECUTIVE

    def test_domain_mapping_unknown_fallback(self):
        """Unknown domain falls back to BIDomain.SALES."""
        row = _make_report_row(domain="custom")
        asset = _row_to_asset(row, tenant_id="t")
        assert asset.urn.domain == BIDomain.SALES

    def test_empty_acl(self):
        """Empty ACL maps correctly."""
        row = _make_report_row(acl=[])
        asset = _row_to_asset(row, tenant_id="t")
        assert asset.acl == []
        assert asset.is_shared is False

    def test_tags_include_domain(self):
        """Tags include 'user-created', 'report', and domain."""
        row = _make_report_row(domain="finance")
        asset = _row_to_asset(row, tenant_id="t")
        assert "user-created" in asset.tags
        assert "report" in asset.tags
        assert "finance" in asset.tags

    def test_tenant_scoped(self):
        """Mapped asset is tenant-scoped (not system-wide)."""
        row = _make_report_row()
        asset = _row_to_asset(row, tenant_id="tenant-abc")
        assert asset.is_system_wide is False
        assert asset.is_tenant_scoped is True

    def test_has_owner(self):
        """Mapped asset has an owner."""
        row = _make_report_row()
        asset = _row_to_asset(row, tenant_id="t")
        assert asset.has_owner is True

    def test_none_description_maps_to_empty(self):
        """None description maps to empty string."""
        row = _make_report_row(description=None)
        asset = _row_to_asset(row, tenant_id="t")
        assert asset.description == ""


# ============================================================================
# 3. Pydantic Schemas — Validation
# ============================================================================

class TestCreateReportSchema:
    """Test CreateReportRequest Pydantic validation."""

    def test_valid_request(self):
        """Valid request passes validation."""
        req = CreateReportRequest(
            title="My Report",
            config=_valid_config(),
        )
        assert req.title == "My Report"
        assert req.domain == "custom"
        assert req.acl == []

    def test_config_requires_widgets(self):
        """Config without widgets is rejected."""
        with pytest.raises(ValidationError):
            ReportConfig(widgets=[])

    def test_config_requires_at_least_one_widget(self):
        """Config with empty widgets list is rejected."""
        with pytest.raises(ValidationError):
            CreateReportRequest(
                title="Bad",
                config=ReportConfig(widgets=[]),
            )

    def test_title_required(self):
        """Title is required."""
        with pytest.raises(ValidationError):
            CreateReportRequest(
                config=_valid_config(),
            )

    def test_title_max_length(self):
        """Title exceeding 256 chars is rejected."""
        with pytest.raises(ValidationError):
            CreateReportRequest(
                title="x" * 257,
                config=_valid_config(),
            )

    def test_acl_validation_valid(self):
        """Valid ACL entries pass."""
        req = CreateReportRequest(
            title="Shared Report",
            config=_valid_config(),
            acl=["user:abc-123", "role:finance", "tenant:*"],
        )
        assert len(req.acl) == 3

    def test_acl_validation_invalid_prefix(self):
        """ACL with invalid prefix is rejected."""
        with pytest.raises(ValidationError):
            CreateReportRequest(
                title="Bad ACL",
                config=_valid_config(),
                acl=["invalid:entry"],
            )

    def test_acl_validation_empty_value(self):
        """ACL with empty value after prefix is rejected."""
        with pytest.raises(ValidationError):
            CreateReportRequest(
                title="Bad ACL",
                config=_valid_config(),
                acl=["user:"],
            )

    def test_with_acl_and_domain(self):
        """Request with custom domain and ACL."""
        table_widget = Widget(
            id="w-table", type=WidgetType.TABLE, title="P&L",
            position=GridPosition(x=0, y=0, w=6, h=3),
            data_source=DataSource(
                view=ViewScope.RECEIVABLES_SUMMARY,
                metrics=[ReportMetric.OUTSTANDING_BALANCE],
            ),
        )
        chart_widget = _valid_widget(wid="w-chart")
        req = CreateReportRequest(
            title="Finance Report",
            domain="finance",
            config=ReportConfig(widgets=[table_widget, chart_widget]),
            acl=["role:finance"],
        )
        assert req.domain == "finance"
        assert len(req.config.widgets) == 2


class TestUpdateReportSchema:
    """Test UpdateReportRequest Pydantic validation."""

    def test_all_fields_optional(self):
        """All fields are optional for partial update."""
        req = UpdateReportRequest()
        assert req.title is None
        assert req.config is None
        assert req.acl is None

    def test_partial_update_title_only(self):
        """Can update just the title."""
        req = UpdateReportRequest(title="New Title")
        assert req.title == "New Title"
        assert req.config is None

    def test_acl_validation_on_update(self):
        """ACL validation also applies on update."""
        with pytest.raises(ValidationError):
            UpdateReportRequest(acl=["bad:prefix"])


# ============================================================================
# 4. DbAssetResolver — resolve() with mocked session
# ============================================================================

class TestDbAssetResolver:
    """Test DbAssetResolver with mocked DB sessions."""

    @pytest.mark.asyncio
    async def test_resolve_non_report_urn_returns_none(self):
        """Non-report URN is immediately rejected."""
        resolver = DbAssetResolver(session_factory=MagicMock())
        result = await resolver.resolve(
            "urn:bi:view:sales:mv_sales_daily",
            tenant_id="tenant-abc",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_no_tenant_returns_none(self):
        """Missing tenant_id returns None."""
        resolver = DbAssetResolver(session_factory=MagicMock())
        rid = uuid.uuid4()
        result = await resolver.resolve(
            f"urn:bi:report:sales:{rid}",
            tenant_id=None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_invalid_uuid_returns_none(self):
        """Invalid UUID in URN returns None."""
        resolver = DbAssetResolver(session_factory=MagicMock())
        result = await resolver.resolve(
            "urn:bi:report:sales:not-a-uuid",
            tenant_id="tenant-abc",
        )
        assert result is None


# ============================================================================
# 5. Cache invalidation integration
# ============================================================================

class TestCacheInvalidationIntegration:
    """Test that cache invalidation works with the resolver flow."""

    def setup_method(self):
        invalidate_all()

    def teardown_method(self):
        invalidate_all()

    def test_create_then_invalidate(self):
        """Simulates: create report → cache → invalidate → cache miss."""
        rid = uuid.uuid4()
        urn = f"urn:bi:report:sales:{rid}"
        row = _make_report_row(report_id=rid)
        asset = _row_to_asset(row, tenant_id="tenant-abc")

        # Simulate resolver caching the asset
        _cache_put(urn, asset)
        assert _cache_get(urn) is not None

        # 🔒 S7-4-C4: Invalidate after mutation
        invalidate_asset(urn)
        assert _cache_get(urn) is None

    def test_update_acl_invalidates(self):
        """Simulates: update ACL → invalidate → next resolve hits DB."""
        rid = uuid.uuid4()
        urn = f"urn:bi:report:sales:{rid}"
        row = _make_report_row(report_id=rid, acl=[])
        asset = _row_to_asset(row, tenant_id="tenant-abc")

        _cache_put(urn, asset)
        assert dynamic_cache_size() == 1

        # ACL change → invalidate
        invalidate_asset(urn)
        assert dynamic_cache_size() == 0

    def test_multiple_reports_selective_invalidation(self):
        """Only the targeted URN is invalidated, others remain cached."""
        rid1 = uuid.uuid4()
        rid2 = uuid.uuid4()
        urn1 = f"urn:bi:report:sales:{rid1}"
        urn2 = f"urn:bi:report:sales:{rid2}"

        asset1 = _row_to_asset(_make_report_row(report_id=rid1), "t")
        asset2 = _row_to_asset(_make_report_row(report_id=rid2), "t")

        _cache_put(urn1, asset1)
        _cache_put(urn2, asset2)
        assert dynamic_cache_size() == 2

        invalidate_asset(urn1)
        assert _cache_get(urn1) is None
        assert _cache_get(urn2) is not None

"""
S7-2 + S7-3: BI Access Enforcement & Audit Trail — Unit Tests.

Tests the HTTP enforcement layer (The Police) and audit trail (The Recorder)
that bridge FastAPI with the S7-1 policy engine (The Law).

Test Strategy:
- Mock the request context (AuthContext, TenantContext) to isolate
  the enforcement layer from the actual HTTP stack.
- Verify that get_policy_subject() correctly builds PolicySubject
  from DB-loaded roles (🔒 S7-1-A compliance).
- Verify RequireBIPermission (declarative) and enforce_bi_access
  (imperative) both delegate to evaluate_policy() and translate
  results into HTTP 403 or PolicyResult.
- Verify fail-safe behavior (missing context → deny).
- Verify tenant isolation produces generic error messages (no info leak).
- Verify audit hook enqueues write_audit_log via BackgroundTasks (S7-3).
- Verify audit failure does not affect business logic (🔒 S7-3-C3).

Test Categories:
    1. get_policy_subject — Trust Boundary
    2. RequireBIPermission — Declarative Enforcement
    3. enforce_bi_access — Imperative Enforcement
    4. Fail-Safe Behavior
    5. Error Detail Security
    6. Audit Hook (S7-3)
    7. Full Request Flow
    8. Audit Writer Service
"""
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from core.governance.models import (
    BIAction,
    BIAsset,
    BIDomain,
    BiUrn,
    DataFreshness,
    ResourceType,
)
from core.governance.policy import (
    PolicySubject,
    PolicyResult,
    POLICY_ADMIN_BYPASS,
    POLICY_DEFAULT_DENY,
    POLICY_ROLE_MATRIX,
    POLICY_TENANT_ISOLATION,
)
from core.governance.registry import get_asset
from api.middleware.bi_access import (
    get_policy_subject,
    RequireBIPermission,
    enforce_bi_access,
    _build_denial_detail,
    _audit_hook,
)
from core.security import TokenPayload


# ============================================================================
# Test Helpers — Mock Request Context
# ============================================================================

@dataclass
class MockRole:
    """Mimics the Role ORM model with a name attribute."""
    name: str
    permissions: list = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


@dataclass
class MockUser:
    """Mimics the User ORM model with roles relationship."""
    roles: List[MockRole]
    is_active: bool = True


def _make_mock_request(
    user_id: str = "user-001",
    tenant_id: str = "tenant-abc",
    tenant_schema: str = "t_abc",
    role_names: list[str] | None = None,
    has_auth: bool = True,
    has_tenant: bool = True,
) -> MagicMock:
    """
    Create a mock FastAPI Request with auth and tenant context on state.

    This simulates what the auth/tenant middleware attaches to request.state
    before the dependency runs.
    """
    if role_names is None:
        role_names = ["viewer"]

    request = MagicMock()
    request.state = SimpleNamespace()

    if has_auth:
        token = TokenPayload(
            user_id=user_id,
            tenant_id=tenant_id,
            tenant_schema=tenant_schema,
        )
        auth_ctx = SimpleNamespace(token=token, raw_token="mock-jwt")
        request.state.auth_context = auth_ctx
    # If has_auth is False, auth_context is not set on state

    if has_tenant:
        roles = [MockRole(name=rn) for rn in role_names]
        user = MockUser(roles=roles)
        tenant_ctx = SimpleNamespace(
            tenant_id=tenant_id,
            tenant_schema=tenant_schema,
            session=MagicMock(),
            user=user,
        )
        request.state.tenant_context = tenant_ctx
    # If has_tenant is False, tenant_context is not set on state

    return request


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def admin_request():
    return _make_mock_request(
        user_id="admin-001",
        tenant_id="tenant-abc",
        role_names=["admin"],
    )


@pytest.fixture
def finance_request():
    return _make_mock_request(
        user_id="finance-001",
        tenant_id="tenant-abc",
        role_names=["finance"],
    )


@pytest.fixture
def viewer_request():
    return _make_mock_request(
        user_id="viewer-001",
        tenant_id="tenant-abc",
        role_names=["viewer"],
    )


@pytest.fixture
def no_auth_request():
    return _make_mock_request(has_auth=False, has_tenant=False)


@pytest.fixture
def no_tenant_request():
    return _make_mock_request(has_auth=True, has_tenant=False)


@pytest.fixture
def other_tenant_request():
    return _make_mock_request(
        user_id="other-001",
        tenant_id="tenant-xyz",
        role_names=["admin"],
    )


@pytest.fixture
def mock_bg_tasks():
    return MagicMock(spec=BackgroundTasks)


@pytest.fixture
def system_asset() -> BIAsset:
    return get_asset("urn:bi:view:sales:mv_sales_daily")


@pytest.fixture
def tenant_asset() -> BIAsset:
    return BIAsset(
        urn=BiUrn(
            resource_type=ResourceType.DASHBOARD,
            domain=BIDomain.FINANCE,
            identifier="custom_tenant_dashboard",
        ),
        display_name="Custom Tenant Dashboard",
        tenant_id="tenant-abc",
        freshness=DataFreshness.REAL_TIME,
    )


# ============================================================================
# 1. get_policy_subject — Trust Boundary Tests
# ============================================================================

class TestGetPolicySubject:
    """Test the Trust Boundary: get_policy_subject()."""

    def test_builds_subject_from_request(self, finance_request):
        """Subject is correctly built from request context."""
        subject = get_policy_subject(finance_request)
        assert isinstance(subject, PolicySubject)
        assert subject.user_id == "finance-001"
        assert subject.tenant_id == "tenant-abc"
        assert subject.roles == frozenset({"finance"})

    def test_roles_from_db_not_token(self, admin_request):
        """🔒 S7-1-A: Roles come from DB user object, not JWT."""
        subject = get_policy_subject(admin_request)
        assert subject.roles == frozenset({"admin"})
        # The token doesn't have roles — they come from tenant_ctx.user.roles

    def test_multiple_roles(self):
        """Subject with multiple DB roles."""
        request = _make_mock_request(role_names=["finance", "sales"])
        subject = get_policy_subject(request)
        assert subject.roles == frozenset({"finance", "sales"})

    def test_no_roles_returns_empty_frozenset(self):
        """User with no roles gets empty frozenset (will be default-denied)."""
        request = _make_mock_request(role_names=[])
        subject = get_policy_subject(request)
        assert subject.roles == frozenset()

    def test_missing_auth_raises_401(self, no_auth_request):
        """Missing auth context raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            get_policy_subject(no_auth_request)
        assert exc_info.value.status_code == 401

    def test_missing_tenant_raises_401(self, no_tenant_request):
        """Missing tenant context raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            get_policy_subject(no_tenant_request)
        assert exc_info.value.status_code == 401


# ============================================================================
# 2. RequireBIPermission — Declarative Enforcement Tests
# ============================================================================

class TestRequireBIPermission:
    """Test the declarative Depends() enforcement."""

    @pytest.mark.asyncio
    async def test_admin_allowed(self, admin_request, mock_bg_tasks):
        """Admin is allowed to VIEW a system-wide asset."""
        enforcer = RequireBIPermission(
            BIAction.VIEW,
            "urn:bi:dashboard:executive:executive_summary",
        )
        result = await enforcer(admin_request, mock_bg_tasks)
        assert isinstance(result, PolicyResult)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    @pytest.mark.asyncio
    async def test_viewer_can_view(self, viewer_request, mock_bg_tasks):
        """Viewer is allowed to VIEW."""
        enforcer = RequireBIPermission(
            BIAction.VIEW,
            "urn:bi:dashboard:executive:executive_summary",
        )
        result = await enforcer(viewer_request, mock_bg_tasks)
        assert result.allowed is True
        assert result.policy_name == POLICY_ROLE_MATRIX

    @pytest.mark.asyncio
    async def test_viewer_cannot_export(self, viewer_request, mock_bg_tasks):
        """Viewer is denied EXPORT — raises 403."""
        enforcer = RequireBIPermission(
            BIAction.EXPORT,
            "urn:bi:export_template:sales:sales_daily_csv",
        )
        with pytest.raises(HTTPException) as exc_info:
            await enforcer(viewer_request, mock_bg_tasks)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "BI_ACCESS_DENIED"

    @pytest.mark.asyncio
    async def test_finance_can_export(self, finance_request, mock_bg_tasks):
        """Finance is allowed to EXPORT."""
        enforcer = RequireBIPermission(
            BIAction.EXPORT,
            "urn:bi:export_template:sales:sales_daily_csv",
        )
        result = await enforcer(finance_request, mock_bg_tasks)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_cross_tenant_denied(self, other_tenant_request, tenant_asset):
        """Cross-tenant access denied even for admin."""
        enforcer = RequireBIPermission(
            BIAction.VIEW,
            tenant_asset.urn_string,
        )
        # tenant_asset has tenant_id="tenant-abc", request has "tenant-xyz"
        # But tenant_asset is not in registry, so we use enforce_bi_access directly
        subject = get_policy_subject(other_tenant_request)
        with pytest.raises(HTTPException) as exc_info:
            enforce_bi_access(subject, BIAction.VIEW, tenant_asset)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_policy_result(self, admin_request, mock_bg_tasks):
        """Successful enforcement returns PolicyResult for audit."""
        enforcer = RequireBIPermission(
            BIAction.VIEW,
            "urn:bi:view:sales:mv_sales_daily",
        )
        result = await enforcer(admin_request, mock_bg_tasks)
        assert isinstance(result, PolicyResult)
        assert result.subject_id == "admin-001"
        assert result.asset_urn == "urn:bi:view:sales:mv_sales_daily"
        assert result.action == "view"

    @pytest.mark.asyncio
    async def test_no_auth_raises_401(self, no_auth_request, mock_bg_tasks):
        """Missing auth context raises 401, not 403."""
        enforcer = RequireBIPermission(
            BIAction.VIEW,
            "urn:bi:view:sales:mv_sales_daily",
        )
        with pytest.raises(HTTPException) as exc_info:
            await enforcer(no_auth_request, mock_bg_tasks)
        assert exc_info.value.status_code == 401


# ============================================================================
# 3. enforce_bi_access — Imperative Enforcement Tests
# ============================================================================

class TestEnforceBIAccess:
    """Test the imperative enforcement function."""

    def test_allow_returns_result(self):
        """Allowed access returns PolicyResult."""
        subject = PolicySubject(
            user_id="admin-001",
            tenant_id="tenant-abc",
            roles=frozenset({"admin"}),
        )
        result = enforce_bi_access(
            subject, BIAction.VIEW, "urn:bi:view:sales:mv_sales_daily"
        )
        assert result.allowed is True

    def test_deny_raises_403(self):
        """Denied access raises HTTPException 403."""
        subject = PolicySubject(
            user_id="viewer-001",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        with pytest.raises(HTTPException) as exc_info:
            enforce_bi_access(
                subject,
                BIAction.EXPORT,
                "urn:bi:export_template:sales:sales_daily_csv",
            )
        assert exc_info.value.status_code == 403

    def test_accepts_biasset_object(self, system_asset):
        """Can pass BIAsset object directly."""
        subject = PolicySubject(
            user_id="admin-001",
            tenant_id="tenant-abc",
            roles=frozenset({"admin"}),
        )
        result = enforce_bi_access(subject, BIAction.VIEW, system_asset)
        assert result.allowed is True

    def test_invalid_urn_failsafe_403(self):
        """Invalid URN triggers fail-safe 403 (not 500)."""
        subject = PolicySubject(
            user_id="admin-001",
            tenant_id="tenant-abc",
            roles=frozenset({"admin"}),
        )
        with pytest.raises(HTTPException) as exc_info:
            enforce_bi_access(
                subject,
                BIAction.VIEW,
                "urn:bi:view:sales:nonexistent_view",
            )
        assert exc_info.value.status_code == 403
        assert "unable to resolve" in exc_info.value.detail["message"]

    def test_tenant_isolation_with_asset_object(self, tenant_asset):
        """Cross-tenant deny with BIAsset object."""
        subject = PolicySubject(
            user_id="other-admin",
            tenant_id="tenant-xyz",
            roles=frozenset({"admin"}),
        )
        with pytest.raises(HTTPException) as exc_info:
            enforce_bi_access(subject, BIAction.VIEW, tenant_asset)
        assert exc_info.value.status_code == 403

    def test_dynamic_urn_scenario(self):
        """Simulates dynamic URN resolution from request body."""
        subject = PolicySubject(
            user_id="finance-001",
            tenant_id="tenant-abc",
            roles=frozenset({"finance"}),
        )
        # Simulate: body.view = "sales" → build URN dynamically
        view_name = "sales"
        dynamic_urn = f"urn:bi:report:{view_name}:adhoc_{view_name}_analysis"
        result = enforce_bi_access(subject, BIAction.INTERACT, dynamic_urn)
        assert result.allowed is True


# ============================================================================
# 4. Fail-Safe Behavior Tests
# ============================================================================

class TestFailSafe:
    """Verify fail-safe: when in doubt, DENY."""

    def test_no_roles_denied(self):
        """User with no roles is denied."""
        subject = PolicySubject(
            user_id="norole-001",
            tenant_id="tenant-abc",
            roles=frozenset(),
        )
        with pytest.raises(HTTPException) as exc_info:
            enforce_bi_access(
                subject,
                BIAction.VIEW,
                "urn:bi:view:sales:mv_sales_daily",
            )
        assert exc_info.value.status_code == 403

    def test_unknown_role_denied(self):
        """User with unrecognized role is denied."""
        subject = PolicySubject(
            user_id="intern-001",
            tenant_id="tenant-abc",
            roles=frozenset({"intern"}),
        )
        with pytest.raises(HTTPException) as exc_info:
            enforce_bi_access(
                subject,
                BIAction.VIEW,
                "urn:bi:view:sales:mv_sales_daily",
            )
        assert exc_info.value.status_code == 403


# ============================================================================
# 5. Error Detail Security Tests
# ============================================================================

class TestErrorDetailSecurity:
    """Verify that error details don't leak sensitive information."""

    def test_tenant_isolation_generic_message(self):
        """Tenant isolation denial uses generic message (no tenant IDs)."""
        result = PolicyResult(
            allowed=False,
            reason="Tenant isolation violation: subject tenant 'tenant-xyz' "
                   "does not match asset tenant 'tenant-abc'",
            policy_name=POLICY_TENANT_ISOLATION,
            subject_id="user-001",
            asset_urn="urn:bi:dashboard:finance:custom",
            action="view",
        )
        detail = _build_denial_detail(result)
        assert detail["code"] == "BI_ACCESS_DENIED"
        assert "tenant" not in detail["message"].lower() or "scope" in detail["message"].lower()
        # Must NOT contain actual tenant IDs
        assert "tenant-xyz" not in detail["message"]
        assert "tenant-abc" not in detail["message"]

    def test_role_denial_includes_action(self):
        """Role-based denial includes the action but not role names."""
        result = PolicyResult(
            allowed=False,
            reason="No policy grants 'export' action for roles [viewer]",
            policy_name=POLICY_DEFAULT_DENY,
            subject_id="user-001",
            asset_urn="urn:bi:export_template:sales:sales_daily_csv",
            action="export",
        )
        detail = _build_denial_detail(result)
        assert "export" in detail["message"]
        # Should NOT expose the internal reason with role names
        assert "viewer" not in detail["message"]

    def test_detail_always_has_code(self):
        """All denial details have a 'code' field."""
        for policy_name in [
            POLICY_TENANT_ISOLATION,
            POLICY_DEFAULT_DENY,
            POLICY_ROLE_MATRIX,
        ]:
            result = PolicyResult(
                allowed=False,
                reason="test",
                policy_name=policy_name,
                subject_id="u",
                asset_urn="urn:bi:view:sales:mv_sales_daily",
                action="view",
            )
            detail = _build_denial_detail(result)
            assert "code" in detail
            assert detail["code"] == "BI_ACCESS_DENIED"


# ============================================================================
# 6. Audit Hook Tests (S7-3)
# ============================================================================

class TestAuditHook:
    """Verify audit hook enqueues write_audit_log via BackgroundTasks."""

    def test_audit_hook_called_on_allow(self, mock_bg_tasks):
        """Audit hook is invoked even on successful access."""
        subject = PolicySubject(
            user_id="admin-001",
            tenant_id="tenant-abc",
            roles=frozenset({"admin"}),
        )
        with patch("api.middleware.bi_access._audit_hook") as mock_hook:
            result = enforce_bi_access(
                subject,
                BIAction.VIEW,
                "urn:bi:view:sales:mv_sales_daily",
                background_tasks=mock_bg_tasks,
            )
            mock_hook.assert_called_once()
            call_arg = mock_hook.call_args[0][0]
            assert isinstance(call_arg, PolicyResult)
            assert call_arg.allowed is True

    def test_audit_hook_called_on_deny(self, mock_bg_tasks):
        """Audit hook is invoked even on denied access."""
        subject = PolicySubject(
            user_id="viewer-001",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        with patch("api.middleware.bi_access._audit_hook") as mock_hook:
            with pytest.raises(HTTPException):
                enforce_bi_access(
                    subject,
                    BIAction.EXPORT,
                    "urn:bi:export_template:sales:sales_daily_csv",
                    background_tasks=mock_bg_tasks,
                )
            mock_hook.assert_called_once()
            call_arg = mock_hook.call_args[0][0]
            assert isinstance(call_arg, PolicyResult)
            assert call_arg.allowed is False

    def test_audit_hook_enqueues_background_task(self, mock_bg_tasks):
        """S7-3: _audit_hook calls background_tasks.add_task with write_audit_log."""
        result = PolicyResult(
            allowed=True,
            reason="Admin bypass",
            policy_name=POLICY_ADMIN_BYPASS,
            subject_id="admin-001",
            asset_urn="urn:bi:view:sales:mv_sales_daily",
            action="view",
        )
        _audit_hook(result, "tenant-abc", mock_bg_tasks)
        mock_bg_tasks.add_task.assert_called_once()
        from services.audit_writer import write_audit_log
        call_args = mock_bg_tasks.add_task.call_args
        assert call_args[0][0] is write_audit_log
        assert call_args[0][1] is result
        assert call_args[0][2] == "tenant-abc"

    def test_audit_hook_skips_when_no_background_tasks(self):
        """S7-3: _audit_hook is a no-op when background_tasks is None."""
        result = PolicyResult(
            allowed=True,
            reason="Admin bypass",
            policy_name=POLICY_ADMIN_BYPASS,
            subject_id="admin-001",
            asset_urn="urn:bi:view:sales:mv_sales_daily",
            action="view",
        )
        # Should not raise
        _audit_hook(result, "tenant-abc", None)

    def test_audit_hook_swallows_enqueue_error(self, mock_bg_tasks):
        """🔒 S7-3-C3: Audit enqueue failure must not propagate."""
        mock_bg_tasks.add_task.side_effect = RuntimeError("queue full")
        result = PolicyResult(
            allowed=True,
            reason="Admin bypass",
            policy_name=POLICY_ADMIN_BYPASS,
            subject_id="admin-001",
            asset_urn="urn:bi:view:sales:mv_sales_daily",
            action="view",
        )
        # Must not raise — audit failure is observable via logger, not exception
        _audit_hook(result, "tenant-abc", mock_bg_tasks)


# ============================================================================
# 7. Integration: Full Request Flow Tests
# ============================================================================

class TestFullRequestFlow:
    """End-to-end tests simulating complete request flows."""

    @pytest.mark.asyncio
    async def test_admin_views_dashboard_full_flow(self, mock_bg_tasks):
        """Admin → get_policy_subject → RequireBIPermission → ALLOW."""
        request = _make_mock_request(
            user_id="ceo-001",
            tenant_id="tenant-abc",
            role_names=["admin"],
        )
        enforcer = RequireBIPermission(
            BIAction.VIEW,
            "urn:bi:dashboard:executive:executive_summary",
        )
        result = await enforcer(request, mock_bg_tasks)
        assert result.allowed is True
        assert result.subject_id == "ceo-001"

    @pytest.mark.asyncio
    async def test_viewer_export_denied_full_flow(self, mock_bg_tasks):
        """Viewer → get_policy_subject → RequireBIPermission → 403."""
        request = _make_mock_request(
            user_id="external-001",
            tenant_id="tenant-abc",
            role_names=["viewer"],
        )
        enforcer = RequireBIPermission(
            BIAction.EXPORT,
            "urn:bi:export_template:sales:sales_daily_csv",
        )
        with pytest.raises(HTTPException) as exc_info:
            await enforcer(request, mock_bg_tasks)
        assert exc_info.value.status_code == 403

    def test_finance_dynamic_export_full_flow(self):
        """Finance → get_policy_subject → enforce_bi_access (dynamic) → ALLOW."""
        request = _make_mock_request(
            user_id="cfo-001",
            tenant_id="tenant-abc",
            role_names=["finance"],
        )
        subject = get_policy_subject(request)
        # Simulate dynamic URN from request body
        result = enforce_bi_access(
            subject,
            BIAction.EXPORT,
            "urn:bi:export_template:sales:sales_daily_csv",
        )
        assert result.allowed is True

    def test_sales_cannot_manage_full_flow(self):
        """Sales → get_policy_subject → enforce_bi_access → 403."""
        request = _make_mock_request(
            user_id="sales-rep-001",
            tenant_id="tenant-abc",
            role_names=["sales"],
        )
        subject = get_policy_subject(request)
        with pytest.raises(HTTPException) as exc_info:
            enforce_bi_access(
                subject,
                BIAction.MANAGE,
                "urn:bi:dashboard:sales:sales_trend",
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_multi_role_user_full_flow(self, mock_bg_tasks):
        """User with sales+finance → can EXPORT (finance grants it)."""
        request = _make_mock_request(
            user_id="multi-001",
            tenant_id="tenant-abc",
            role_names=["sales", "finance"],
        )
        enforcer = RequireBIPermission(
            BIAction.EXPORT,
            "urn:bi:export_template:sales:sales_daily_csv",
        )
        result = await enforcer(request, mock_bg_tasks)
        assert result.allowed is True

    def test_audit_enqueued_on_full_flow(self, mock_bg_tasks):
        """S7-3: BackgroundTasks.add_task is called during full enforcement flow."""
        request = _make_mock_request(
            user_id="admin-001",
            tenant_id="tenant-abc",
            role_names=["admin"],
        )
        subject = get_policy_subject(request)
        enforce_bi_access(
            subject,
            BIAction.VIEW,
            "urn:bi:view:sales:mv_sales_daily",
            background_tasks=mock_bg_tasks,
        )
        mock_bg_tasks.add_task.assert_called_once()


# ============================================================================
# 8. Audit Writer Service Tests
# ============================================================================

class TestAuditWriterService:
    """Test the write_audit_log service function."""

    @pytest.mark.asyncio
    async def test_write_audit_log_creates_entry(self):
        """write_audit_log creates a SysAuditLog entry (mocked session)."""
        from services.audit_writer import write_audit_log

        result = PolicyResult(
            allowed=True,
            reason="Admin bypass",
            policy_name=POLICY_ADMIN_BYPASS,
            subject_id="admin-001",
            asset_urn="urn:bi:view:sales:mv_sales_daily",
            action="view",
        )

        mock_session = AsyncMock()
        mock_session.info = {}
        mock_session.add = MagicMock()  # add() is synchronous
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("services.audit_writer.AsyncSessionLocal", return_value=mock_session):
            await write_audit_log(result, "tenant-abc")

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.actor_id == "admin-001"
        assert added_obj.tenant_id == "tenant-abc"
        assert added_obj.action == "view"
        assert added_obj.allowed is True

    @pytest.mark.asyncio
    async def test_write_audit_log_swallows_db_error(self):
        """🔒 S7-3-C3: DB failure in write_audit_log must not propagate."""
        from services.audit_writer import write_audit_log

        result = PolicyResult(
            allowed=False,
            reason="Default deny",
            policy_name=POLICY_DEFAULT_DENY,
            subject_id="viewer-001",
            asset_urn="urn:bi:view:sales:mv_sales_daily",
            action="export",
        )

        mock_session = AsyncMock()
        mock_session.info = {}
        mock_session.add = MagicMock()  # add() is synchronous
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit.side_effect = RuntimeError("DB connection lost")

        # Must not raise
        with patch("services.audit_writer.AsyncSessionLocal", return_value=mock_session):
            await write_audit_log(result, "tenant-abc")

    @pytest.mark.asyncio
    async def test_write_audit_log_with_metadata(self):
        """write_audit_log passes metadata to SysAuditLog."""
        from services.audit_writer import write_audit_log

        result = PolicyResult(
            allowed=True,
            reason="Admin bypass",
            policy_name=POLICY_ADMIN_BYPASS,
            subject_id="admin-001",
            asset_urn="urn:bi:view:sales:mv_sales_daily",
            action="view",
        )

        mock_session = AsyncMock()
        mock_session.info = {}
        mock_session.add = MagicMock()  # add() is synchronous
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        metadata = {"request_id": "req-123", "ip": "10.0.0.1"}
        with patch("services.audit_writer.AsyncSessionLocal", return_value=mock_session):
            await write_audit_log(result, "tenant-abc", metadata=metadata)

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.metadata_ == metadata

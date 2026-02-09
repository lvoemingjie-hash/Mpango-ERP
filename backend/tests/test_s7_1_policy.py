"""
S7-1: BI Policy Engine — Unit Tests.

Tests the pure-logic policy engine without any web framework dependencies.
Covers all four evaluation steps in frozen order:
    1. Tenant Isolation
    2. Admin Bypass
    3. Role-Action Matrix (Baseline)
    4. Default Deny

Test Categories:
    - Tenant Isolation (cross-tenant deny, system-wide allow)
    - Admin Bypass (admin within tenant, admin cross-tenant denied)
    - Role-Action Matrix (finance, sales, warehouse, viewer)
    - Default Deny (unknown role, no roles)
    - Edge Cases (multiple roles, URN string input, invalid input)
    - PolicySubject validation
    - PolicyResult structure
    - Roles module helpers
"""
import pytest

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
    evaluate_policy,
    POLICY_TENANT_ISOLATION,
    POLICY_ADMIN_BYPASS,
    POLICY_ROLE_MATRIX,
    POLICY_DEFAULT_DENY,
)
from core.governance.roles import (
    ADMIN_ROLE_NAME,
    DEFAULT_BI_PERMISSIONS,
    get_allowed_actions,
    is_action_allowed_for_role,
    list_roles_with_action,
)
from core.governance.registry import get_asset, GOVERNANCE_REGISTRY


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def system_asset() -> BIAsset:
    """A system-wide asset (tenant_id=None) — accessible to all tenants."""
    return get_asset("urn:bi:view:sales:mv_sales_daily")


@pytest.fixture
def tenant_asset() -> BIAsset:
    """A tenant-scoped asset — only accessible to matching tenant."""
    return BIAsset(
        urn=BiUrn(
            resource_type=ResourceType.DASHBOARD,
            domain=BIDomain.FINANCE,
            identifier="custom_tenant_dashboard",
        ),
        display_name="Custom Tenant Dashboard",
        description="A tenant-specific custom dashboard",
        tenant_id="tenant-abc",
        freshness=DataFreshness.REAL_TIME,
    )


@pytest.fixture
def admin_subject() -> PolicySubject:
    return PolicySubject(
        user_id="admin-user-001",
        tenant_id="tenant-abc",
        roles=frozenset({"admin"}),
    )


@pytest.fixture
def finance_subject() -> PolicySubject:
    return PolicySubject(
        user_id="finance-user-001",
        tenant_id="tenant-abc",
        roles=frozenset({"finance"}),
    )


@pytest.fixture
def sales_subject() -> PolicySubject:
    return PolicySubject(
        user_id="sales-user-001",
        tenant_id="tenant-abc",
        roles=frozenset({"sales"}),
    )


@pytest.fixture
def warehouse_subject() -> PolicySubject:
    return PolicySubject(
        user_id="warehouse-user-001",
        tenant_id="tenant-abc",
        roles=frozenset({"warehouse"}),
    )


@pytest.fixture
def viewer_subject() -> PolicySubject:
    return PolicySubject(
        user_id="viewer-user-001",
        tenant_id="tenant-abc",
        roles=frozenset({"viewer"}),
    )


@pytest.fixture
def other_tenant_subject() -> PolicySubject:
    """Subject from a DIFFERENT tenant."""
    return PolicySubject(
        user_id="other-user-001",
        tenant_id="tenant-xyz",
        roles=frozenset({"admin"}),
    )


@pytest.fixture
def no_role_subject() -> PolicySubject:
    """Subject with no roles at all."""
    return PolicySubject(
        user_id="norole-user-001",
        tenant_id="tenant-abc",
        roles=frozenset(),
    )


# ============================================================================
# 1. Tenant Isolation Tests
# ============================================================================

class TestTenantIsolation:
    """Step 1: Tenant isolation is ALWAYS checked first."""

    def test_cross_tenant_deny_even_admin(
        self, other_tenant_subject, tenant_asset
    ):
        """Admin of Tenant XYZ cannot access Tenant ABC's asset."""
        result = evaluate_policy(
            other_tenant_subject, BIAction.VIEW, tenant_asset
        )
        assert result.allowed is False
        assert result.policy_name == POLICY_TENANT_ISOLATION
        assert "tenant-xyz" in result.reason
        assert "tenant-abc" in result.reason

    def test_cross_tenant_deny_all_actions(
        self, other_tenant_subject, tenant_asset
    ):
        """Every action is denied for cross-tenant access."""
        for action in BIAction:
            result = evaluate_policy(
                other_tenant_subject, action, tenant_asset
            )
            assert result.allowed is False
            assert result.policy_name == POLICY_TENANT_ISOLATION

    def test_system_wide_asset_accessible_to_any_tenant(
        self, other_tenant_subject, system_asset
    ):
        """System-wide assets (tenant_id=None) are accessible to all tenants."""
        result = evaluate_policy(
            other_tenant_subject, BIAction.VIEW, system_asset
        )
        # Should pass tenant check (system-wide) → admin bypass → ALLOW
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_same_tenant_passes_isolation(
        self, finance_subject, tenant_asset
    ):
        """Same tenant passes the isolation check."""
        result = evaluate_policy(
            finance_subject, BIAction.VIEW, tenant_asset
        )
        assert result.allowed is True
        assert result.policy_name != POLICY_TENANT_ISOLATION


# ============================================================================
# 2. Admin Bypass Tests
# ============================================================================

class TestAdminBypass:
    """Step 2: Admin bypass — after tenant isolation."""

    def test_admin_can_view(self, admin_subject, system_asset):
        result = evaluate_policy(admin_subject, BIAction.VIEW, system_asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_admin_can_interact(self, admin_subject, system_asset):
        result = evaluate_policy(admin_subject, BIAction.INTERACT, system_asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_admin_can_export(self, admin_subject, system_asset):
        result = evaluate_policy(admin_subject, BIAction.EXPORT, system_asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_admin_can_manage(self, admin_subject, system_asset):
        result = evaluate_policy(admin_subject, BIAction.MANAGE, system_asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_admin_all_actions_allowed(self, admin_subject, system_asset):
        """Admin is allowed every BIAction on system-wide assets."""
        for action in BIAction:
            result = evaluate_policy(admin_subject, action, system_asset)
            assert result.allowed is True
            assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_admin_cross_tenant_still_denied(
        self, other_tenant_subject, tenant_asset
    ):
        """Admin bypass does NOT override tenant isolation."""
        result = evaluate_policy(
            other_tenant_subject, BIAction.VIEW, tenant_asset
        )
        assert result.allowed is False
        assert result.policy_name == POLICY_TENANT_ISOLATION


# ============================================================================
# 3. Role-Action Matrix Tests
# ============================================================================

class TestRoleActionMatrix:
    """Step 3: Baseline role-action matrix."""

    # --- Finance: VIEW, INTERACT, EXPORT ---

    def test_finance_can_view(self, finance_subject, system_asset):
        result = evaluate_policy(finance_subject, BIAction.VIEW, system_asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ROLE_MATRIX

    def test_finance_can_interact(self, finance_subject, system_asset):
        result = evaluate_policy(
            finance_subject, BIAction.INTERACT, system_asset
        )
        assert result.allowed is True
        assert result.policy_name == POLICY_ROLE_MATRIX

    def test_finance_can_export(self, finance_subject, system_asset):
        result = evaluate_policy(
            finance_subject, BIAction.EXPORT, system_asset
        )
        assert result.allowed is True
        assert result.policy_name == POLICY_ROLE_MATRIX

    def test_finance_cannot_manage(self, finance_subject, system_asset):
        result = evaluate_policy(
            finance_subject, BIAction.MANAGE, system_asset
        )
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY

    # --- Sales: VIEW, INTERACT ---

    def test_sales_can_view(self, sales_subject, system_asset):
        result = evaluate_policy(sales_subject, BIAction.VIEW, system_asset)
        assert result.allowed is True

    def test_sales_can_interact(self, sales_subject, system_asset):
        result = evaluate_policy(
            sales_subject, BIAction.INTERACT, system_asset
        )
        assert result.allowed is True

    def test_sales_cannot_export(self, sales_subject, system_asset):
        result = evaluate_policy(
            sales_subject, BIAction.EXPORT, system_asset
        )
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY

    def test_sales_cannot_manage(self, sales_subject, system_asset):
        result = evaluate_policy(
            sales_subject, BIAction.MANAGE, system_asset
        )
        assert result.allowed is False

    # --- Warehouse: VIEW only ---

    def test_warehouse_can_view(self, warehouse_subject, system_asset):
        result = evaluate_policy(
            warehouse_subject, BIAction.VIEW, system_asset
        )
        assert result.allowed is True

    def test_warehouse_cannot_interact(self, warehouse_subject, system_asset):
        result = evaluate_policy(
            warehouse_subject, BIAction.INTERACT, system_asset
        )
        assert result.allowed is False

    def test_warehouse_cannot_export(self, warehouse_subject, system_asset):
        result = evaluate_policy(
            warehouse_subject, BIAction.EXPORT, system_asset
        )
        assert result.allowed is False

    def test_warehouse_cannot_manage(self, warehouse_subject, system_asset):
        result = evaluate_policy(
            warehouse_subject, BIAction.MANAGE, system_asset
        )
        assert result.allowed is False

    # --- Viewer: VIEW only ---

    def test_viewer_can_view(self, viewer_subject, system_asset):
        result = evaluate_policy(viewer_subject, BIAction.VIEW, system_asset)
        assert result.allowed is True

    def test_viewer_cannot_interact(self, viewer_subject, system_asset):
        result = evaluate_policy(
            viewer_subject, BIAction.INTERACT, system_asset
        )
        assert result.allowed is False

    def test_viewer_cannot_export(self, viewer_subject, system_asset):
        result = evaluate_policy(
            viewer_subject, BIAction.EXPORT, system_asset
        )
        assert result.allowed is False


# ============================================================================
# 4. Default Deny Tests
# ============================================================================

class TestDefaultDeny:
    """Step 4: Default deny — no matching policy."""

    def test_no_roles_denied(self, no_role_subject, system_asset):
        """Subject with no roles is denied everything."""
        for action in BIAction:
            result = evaluate_policy(no_role_subject, action, system_asset)
            assert result.allowed is False
            assert result.policy_name == POLICY_DEFAULT_DENY

    def test_unknown_role_denied(self, system_asset):
        """Subject with an unrecognized role is denied."""
        subject = PolicySubject(
            user_id="unknown-001",
            tenant_id="tenant-abc",
            roles=frozenset({"intern"}),
        )
        result = evaluate_policy(subject, BIAction.VIEW, system_asset)
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY
        assert "intern" in result.reason

    def test_default_deny_reason_includes_roles(self, system_asset):
        """Deny reason lists the subject's roles for debugging."""
        subject = PolicySubject(
            user_id="test-001",
            tenant_id="tenant-abc",
            roles=frozenset({"sales"}),
        )
        result = evaluate_policy(subject, BIAction.EXPORT, system_asset)
        assert result.allowed is False
        assert "sales" in result.reason


# ============================================================================
# 5. Multiple Roles Tests
# ============================================================================

class TestMultipleRoles:
    """Subject with multiple roles — most permissive wins."""

    def test_sales_plus_finance_can_export(self, system_asset):
        """If user has both sales and finance, finance grants EXPORT."""
        subject = PolicySubject(
            user_id="multi-001",
            tenant_id="tenant-abc",
            roles=frozenset({"sales", "finance"}),
        )
        result = evaluate_policy(subject, BIAction.EXPORT, system_asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ROLE_MATRIX
        assert "finance" in result.reason

    def test_viewer_plus_warehouse_still_view_only(self, system_asset):
        """viewer + warehouse = still only VIEW."""
        subject = PolicySubject(
            user_id="multi-002",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer", "warehouse"}),
        )
        result = evaluate_policy(subject, BIAction.INTERACT, system_asset)
        assert result.allowed is False

    def test_any_role_plus_admin_gets_bypass(self, system_asset):
        """If admin is in the role set, admin bypass kicks in."""
        subject = PolicySubject(
            user_id="multi-003",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer", "admin"}),
        )
        result = evaluate_policy(subject, BIAction.MANAGE, system_asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS


# ============================================================================
# 6. URN String Input Tests
# ============================================================================

class TestUrnStringInput:
    """evaluate_policy() accepts URN strings as asset argument."""

    def test_urn_string_resolved(self, admin_subject):
        """Passing a URN string resolves to the registered asset."""
        result = evaluate_policy(
            admin_subject,
            BIAction.VIEW,
            "urn:bi:view:sales:mv_sales_daily",
        )
        assert result.allowed is True
        assert result.asset_urn == "urn:bi:view:sales:mv_sales_daily"

    def test_invalid_urn_string_raises(self, admin_subject):
        """Passing an unregistered URN raises ValueError."""
        with pytest.raises(ValueError, match="not found in governance registry"):
            evaluate_policy(
                admin_subject,
                BIAction.VIEW,
                "urn:bi:view:sales:nonexistent_view",
            )

    def test_invalid_type_raises(self, admin_subject):
        """Passing a non-string, non-BIAsset raises TypeError."""
        with pytest.raises(TypeError, match="must be BIAsset or URN string"):
            evaluate_policy(admin_subject, BIAction.VIEW, 12345)


# ============================================================================
# 7. PolicySubject Validation Tests
# ============================================================================

class TestPolicySubjectValidation:
    """PolicySubject model validation."""

    def test_empty_user_id_rejected(self):
        with pytest.raises(Exception):
            PolicySubject(
                user_id="",
                tenant_id="tenant-abc",
                roles=frozenset({"viewer"}),
            )

    def test_empty_tenant_id_rejected(self):
        with pytest.raises(Exception):
            PolicySubject(
                user_id="user-001",
                tenant_id="",
                roles=frozenset({"viewer"}),
            )

    def test_roles_from_list(self):
        """Roles can be provided as a list (coerced to frozenset)."""
        subject = PolicySubject(
            user_id="user-001",
            tenant_id="tenant-abc",
            roles=["finance", "sales"],
        )
        assert isinstance(subject.roles, frozenset)
        assert subject.roles == frozenset({"finance", "sales"})

    def test_roles_from_set(self):
        """Roles can be provided as a set (coerced to frozenset)."""
        subject = PolicySubject(
            user_id="user-001",
            tenant_id="tenant-abc",
            roles={"warehouse"},
        )
        assert isinstance(subject.roles, frozenset)

    def test_is_admin_property(self):
        admin = PolicySubject(
            user_id="a", tenant_id="t", roles=frozenset({"admin"})
        )
        non_admin = PolicySubject(
            user_id="a", tenant_id="t", roles=frozenset({"viewer"})
        )
        assert admin.is_admin is True
        assert non_admin.is_admin is False

    def test_subject_is_frozen(self):
        """PolicySubject is immutable."""
        subject = PolicySubject(
            user_id="user-001",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        with pytest.raises(Exception):
            subject.user_id = "changed"


# ============================================================================
# 8. PolicyResult Structure Tests
# ============================================================================

class TestPolicyResultStructure:
    """PolicyResult contains all audit-required fields."""

    def test_result_has_all_audit_fields(self, admin_subject, system_asset):
        result = evaluate_policy(admin_subject, BIAction.VIEW, system_asset)
        assert result.subject_id == admin_subject.user_id
        assert result.asset_urn == system_asset.urn_string
        assert result.action == BIAction.VIEW.value
        assert isinstance(result.reason, str)
        assert isinstance(result.policy_name, str)
        assert isinstance(result.allowed, bool)

    def test_result_is_frozen(self, admin_subject, system_asset):
        result = evaluate_policy(admin_subject, BIAction.VIEW, system_asset)
        with pytest.raises(Exception):
            result.allowed = False


# ============================================================================
# 9. Roles Module Helper Tests
# ============================================================================

class TestRolesHelpers:
    """Test the roles.py helper functions."""

    def test_admin_not_in_matrix(self):
        """Admin is intentionally absent from the baseline matrix."""
        assert "admin" not in DEFAULT_BI_PERMISSIONS

    def test_get_allowed_actions_finance(self):
        actions = get_allowed_actions("finance")
        assert BIAction.VIEW in actions
        assert BIAction.INTERACT in actions
        assert BIAction.EXPORT in actions
        assert BIAction.MANAGE not in actions

    def test_get_allowed_actions_unknown_role(self):
        actions = get_allowed_actions("intern")
        assert actions == frozenset()

    def test_is_action_allowed_for_role(self):
        assert is_action_allowed_for_role("sales", BIAction.VIEW) is True
        assert is_action_allowed_for_role("sales", BIAction.EXPORT) is False

    def test_list_roles_with_action_view(self):
        roles = list_roles_with_action(BIAction.VIEW)
        assert "finance" in roles
        assert "sales" in roles
        assert "warehouse" in roles
        assert "viewer" in roles

    def test_list_roles_with_action_export(self):
        roles = list_roles_with_action(BIAction.EXPORT)
        assert "finance" in roles
        assert "sales" not in roles
        assert "warehouse" not in roles

    def test_list_roles_with_action_manage(self):
        roles = list_roles_with_action(BIAction.MANAGE)
        assert len(roles) == 0


# ============================================================================
# 10. Integration: Full Scenario Tests
# ============================================================================

class TestFullScenarios:
    """End-to-end scenarios combining multiple policy rules."""

    def test_scenario_finance_exports_sales_view(self):
        """Finance user exports the sales daily view — ALLOWED."""
        subject = PolicySubject(
            user_id="cfo-001",
            tenant_id="tenant-abc",
            roles=frozenset({"finance"}),
        )
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ROLE_MATRIX

    def test_scenario_sales_views_dashboard(self):
        """Sales user views the executive dashboard — ALLOWED."""
        subject = PolicySubject(
            user_id="sales-rep-001",
            tenant_id="tenant-abc",
            roles=frozenset({"sales"}),
        )
        asset = get_asset("urn:bi:dashboard:executive:executive_summary")
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is True

    def test_scenario_viewer_tries_export(self):
        """Viewer tries to export — DENIED."""
        subject = PolicySubject(
            user_id="external-001",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        asset = get_asset("urn:bi:export_template:sales:sales_daily_csv")
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY

    def test_scenario_admin_of_other_tenant_denied(self):
        """Admin of Tenant B tries to access Tenant A's custom dashboard."""
        tenant_a_asset = BIAsset(
            urn=BiUrn(
                resource_type=ResourceType.DASHBOARD,
                domain=BIDomain.EXECUTIVE,
                identifier="tenant_a_custom",
            ),
            display_name="Tenant A Custom",
            tenant_id="tenant-aaa",
        )
        tenant_b_admin = PolicySubject(
            user_id="admin-b",
            tenant_id="tenant-bbb",
            roles=frozenset({"admin"}),
        )
        result = evaluate_policy(
            tenant_b_admin, BIAction.VIEW, tenant_a_asset
        )
        assert result.allowed is False
        assert result.policy_name == POLICY_TENANT_ISOLATION

    def test_scenario_warehouse_interacts_denied(self):
        """Warehouse user tries to interact with chart — DENIED."""
        subject = PolicySubject(
            user_id="warehouse-001",
            tenant_id="tenant-abc",
            roles=frozenset({"warehouse"}),
        )
        asset = get_asset("urn:bi:dashboard:sales:sales_trend")
        result = evaluate_policy(subject, BIAction.INTERACT, asset)
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY

    def test_scenario_all_registered_assets_accessible_to_admin(self):
        """Admin can access every registered asset with every action."""
        admin = PolicySubject(
            user_id="superadmin",
            tenant_id="tenant-abc",
            roles=frozenset({"admin"}),
        )
        for urn, asset in GOVERNANCE_REGISTRY.items():
            for action in BIAction:
                result = evaluate_policy(admin, action, asset)
                assert result.allowed is True, (
                    f"Admin denied {action.value} on {urn}"
                )

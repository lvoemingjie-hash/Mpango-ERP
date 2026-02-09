"""
P7-0 + S7-4: Governance Models — Action Taxonomy, URN System, and BI Asset Definition.

Philosophy: "If it's not in the Registry, management can't see it."

This module transforms Phase 6's implicit reporting objects (views, metrics,
dimensions) into explicit, addressable governance assets. Every BI resource
gets a URN (Uniform Resource Name) that uniquely identifies it across the
system, independent of its database representation.

Design Principles:
1. Action Taxonomy — BI operations have business semantics beyond CRUD.
   VIEW ≠ READ. EXPORT ≠ DOWNLOAD. INTERACT ≠ UPDATE.
2. URN Addressing — Every asset is globally addressable via a structured
   identifier: urn:bi:<type>:<domain>:<id>
   🔒 S7-4-C1: URN does NOT carry tenant_id. Tenant is a data attribute,
   not part of the identifier. This ensures URN stability across tenant
   lifecycle events (migration, copy, template).
3. Tenant Awareness — Assets can be system-wide (shared) or tenant-scoped.
   The tenant_id field on BIAsset is the data attribute for tenant scope.
4. Ownership & ACL (S7-4) — Tenant-created assets have an owner_id and
   an optional ACL for sharing. ACL is an independent authorization channel
   with a hard ceiling of EXPORT (🔒 S7-4-C3′).
5. No Enforcement — This module defines the MODEL only. No middleware,
   no RBAC checks, no if-statements. Pure data structures.

Boot Contract Compliance:
- New file in core/governance/ (no modification to frozen core/ files)
- No database changes (in-memory model only)
- No imports from api.v1, api.middleware, or api.dependencies
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# 1. Action Taxonomy — Business-semantic BI operations
# ============================================================================

class BIAction(str, Enum):
    """
    BI-specific action taxonomy.

    These are NOT CRUD operations. They represent the business semantics
    of interacting with BI assets in a governed enterprise context.

    Hierarchy (least → most privileged):
        VIEW < INTERACT < EXPORT < MANAGE

    Future P7-x will map (Role, BIAsset, BIAction) → Allow/Deny.
    This module only defines the vocabulary.
    """
    VIEW = "view"
    """Passive consumption of pre-rendered dashboards and KPI cards.
    The user sees data but cannot change parameters.
    Maps to: GET /dashboards/kpi/summary (S6-3 Tier 1)."""

    INTERACT = "interact"
    """Active exploration: adjusting filters, date ranges, dimensions.
    The user can slice data but cannot extract it from the system.
    Maps to: GET /dashboards/charts/* (S6-3 Tier 2),
             POST /reports/analyze (S6-3 Tier 3)."""

    EXPORT = "export"
    """Trigger async data extraction (CSV/XLSX). High-cost operation
    that produces downloadable artifacts outside the system boundary.
    Maps to: POST /exports (S6-4)."""

    MANAGE = "manage"
    """Create, modify, publish, or retire BI assets (dashboards, reports,
    saved queries). Administrative action for BI asset lifecycle.
    Maps to: Future P7-x asset management endpoints."""


# ============================================================================
# 2. Resource Type — Classification of BI assets
# ============================================================================

class ResourceType(str, Enum):
    """
    Classification of BI assets in the governance model.

    Each type represents a distinct category of governed resource.
    The URN encodes this as the <type> segment.
    """
    DASHBOARD = "dashboard"
    """A composed view of multiple widgets (KPI cards, charts).
    Example URN: urn:bi:dashboard:finance:executive_summary"""

    REPORT = "report"
    """A structured data output (table, pivot) from ad-hoc analysis.
    Example URN: urn:bi:report:sales:daily_breakdown"""

    METRIC = "metric"
    """A single measurable business quantity (revenue, balance).
    Example URN: urn:bi:metric:finance:net_mrr"""

    VIEW = "view"
    """A database reporting object (rpt_* or mv_*) that backs metrics.
    Example URN: urn:bi:view:finance:mv_sales_daily"""

    EXPORT_TEMPLATE = "export_template"
    """A saved export configuration (view + metrics + filters + format).
    Example URN: urn:bi:export_template:sales:monthly_revenue_csv"""


# ============================================================================
# 3. Business Domain — Organizational grouping of BI assets
# ============================================================================

class BIDomain(str, Enum):
    """
    Business domain classification for BI assets.

    Domains group assets by organizational function. This enables
    domain-scoped governance policies in future phases.
    """
    FINANCE = "finance"
    """Cash flow, receivables, ledger-derived metrics."""

    SALES = "sales"
    """Revenue, transactions, order-derived metrics."""

    OPERATIONS = "operations"
    """Inventory, procurement, logistics metrics (future)."""

    EXECUTIVE = "executive"
    """Cross-domain summary dashboards for leadership."""


# ============================================================================
# 4. URN — Uniform Resource Name for BI assets
# ============================================================================

URN_PREFIX = "urn:bi"
URN_SEPARATOR = ":"
URN_SEGMENT_COUNT = 5  # urn:bi:<type>:<domain>:<id>


class BiUrn(BaseModel):
    """
    Parsed representation of a BI asset URN.

    Format: urn:bi:<resource_type>:<domain>:<identifier>

    Examples:
        urn:bi:dashboard:finance:executive_summary
        urn:bi:view:sales:mv_sales_daily
        urn:bi:metric:finance:outstanding_balance

    The URN is the canonical, human-readable identifier for any BI asset.
    It is stable across environments (dev/staging/prod) and independent
    of database IDs or internal object references.
    """
    resource_type: ResourceType
    domain: BIDomain
    identifier: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
        description="Unique name within the (type, domain) namespace. "
                    "Lowercase alphanumeric, underscores, and hyphens. "
                    "System assets use snake_case (e.g., mv_sales_daily). "
                    "Tenant assets use UUID (e.g., a1b2c3d4-e5f6-...)."
    )

    @property
    def urn(self) -> str:
        """Render the full URN string."""
        return (
            f"{URN_PREFIX}{URN_SEPARATOR}"
            f"{self.resource_type.value}{URN_SEPARATOR}"
            f"{self.domain.value}{URN_SEPARATOR}"
            f"{self.identifier}"
        )

    @classmethod
    def parse(cls, urn_string: str) -> BiUrn:
        """
        Parse a URN string into a BiUrn object.

        Args:
            urn_string: Full URN (e.g., "urn:bi:view:finance:mv_sales_daily")

        Returns:
            Parsed BiUrn instance.

        Raises:
            ValueError: If the URN format is invalid.
        """
        parts = urn_string.split(URN_SEPARATOR)
        if len(parts) != URN_SEGMENT_COUNT:
            raise ValueError(
                f"Invalid URN format: expected {URN_SEGMENT_COUNT} segments "
                f"(urn:bi:<type>:<domain>:<id>), got {len(parts)}: '{urn_string}'"
            )
        if parts[0] != "urn" or parts[1] != "bi":
            raise ValueError(
                f"Invalid URN prefix: expected 'urn:bi', got '{parts[0]}:{parts[1]}'"
            )
        return cls(
            resource_type=ResourceType(parts[2]),
            domain=BIDomain(parts[3]),
            identifier=parts[4],
        )

    def __str__(self) -> str:
        return self.urn

    def __repr__(self) -> str:
        return f"BiUrn('{self.urn}')"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, BiUrn):
            return self.urn == other.urn
        if isinstance(other, str):
            return self.urn == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.urn)

    model_config = {"frozen": True}


# ============================================================================
# 5. BI Asset — The governed resource object
# ============================================================================

class DataFreshness(str, Enum):
    """How fresh the data behind this asset is."""
    REAL_TIME = "real_time"
    """Backed by a standard view (rpt_*). Always current."""

    NEAR_REAL_TIME = "near_real_time"
    """Backed by a materialized view (mv_*). Refreshed periodically."""

    SNAPSHOT = "snapshot"
    """Point-in-time export or cached result."""


# ============================================================================
# 5a. ACL Constants (S7-4)
# ============================================================================

ACL_MAX_ACTIONS: frozenset[BIAction] = frozenset({
    BIAction.VIEW,
    BIAction.INTERACT,
    BIAction.EXPORT,
})
"""
🔒 S7-4-C3′ (CTO Mandate, Frozen):
    ACL is an independent authorization channel with a hard ceiling.
    ACL can grant VIEW, INTERACT, EXPORT — but NEVER MANAGE.
    ACL is a sharing mechanism, not an authorization escalation tool.
    MANAGE is reserved for asset owner and admin only.
"""


class BIAsset(BaseModel):
    """
    A governed BI resource in the Mpango ERP system.

    This is the central object of the governance model. Every reporting
    view, metric, dashboard, and export template is represented as a
    BIAsset with a unique URN.

    Attributes:
        urn: Globally unique identifier (urn:bi:<type>:<domain>:<id>).
             🔒 S7-4-C1: URN does NOT carry tenant_id.
        display_name: Human-readable name for UI and management reports.
        description: Business-level description of what this asset represents.
        owner: Team or role responsible for this asset's accuracy.
        freshness: Data freshness classification.
        source_phase: Which implementation phase created this asset.
        semantic_ref: Optional back-reference to the semantic layer enum
                      value (e.g., ViewScope.SALES_DAILY).
        tenant_id: Optional tenant scope. None = system-wide (shared).
        owner_id: Optional user ID of the asset creator (S7-4).
                  None for system assets. Set for tenant-created assets.
        acl: Access Control List for sharing (S7-4).
             Entries: "user:<uuid>", "role:<name>", "tenant:*".
             🔒 S7-4-C3′: ACL grants VIEW/INTERACT/EXPORT only, never MANAGE.
        tags: Freeform tags for filtering and discovery.
        created_at: When this asset was registered.
        deprecated: Whether this asset is marked for retirement.
    """
    urn: BiUrn
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Human-readable asset name"
    )
    description: str = Field(
        default="",
        max_length=2048,
        description="Business-level description"
    )
    owner: str = Field(
        default="backend-engineering",
        description="Team or role responsible for this asset"
    )
    freshness: DataFreshness = Field(
        default=DataFreshness.REAL_TIME,
        description="Data freshness classification"
    )
    source_phase: str = Field(
        default="S6",
        description="Implementation phase that created this asset"
    )
    semantic_ref: Optional[str] = Field(
        default=None,
        description="Back-reference to semantic layer enum value "
                    "(e.g., 'ViewScope.SALES_DAILY', 'ReportMetric.REVENUE')"
    )
    tenant_id: Optional[str] = Field(
        default=None,
        description="Tenant scope. None = system-wide shared asset. "
                    "Set for tenant-specific custom reports."
    )
    # S7-4: Ownership
    owner_id: Optional[str] = Field(
        default=None,
        description="User ID of the asset creator/owner. "
                    "None for system assets. Set for tenant-created assets."
    )
    # S7-4: Access Control List
    acl: list[str] = Field(
        default_factory=list,
        description="Access Control List for sharing. Entries are prefixed:\n"
                    "  'user:<user_id>' — specific user grant\n"
                    "  'role:<role_name>' — role-based grant\n"
                    "  'tenant:*' — all users in the asset's tenant\n"
                    "Empty ACL on a tenant asset = owner-only access.\n"
                    "🔒 S7-4-C3′: ACL grants VIEW/INTERACT/EXPORT only, never MANAGE."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Freeform tags for filtering and discovery"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 registration timestamp"
    )
    deprecated: bool = Field(
        default=False,
        description="Whether this asset is marked for retirement"
    )

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id_format(cls, v: Optional[str]) -> Optional[str]:
        """If tenant_id is set, it must be non-empty."""
        if v is not None and not v.strip():
            raise ValueError("tenant_id must be non-empty if provided")
        return v

    @field_validator("acl", mode="before")
    @classmethod
    def validate_acl_entries(cls, v: list[str]) -> list[str]:
        """Validate ACL entry format: must be 'user:<id>', 'role:<name>', or 'tenant:*'."""
        if v is None:
            return []
        valid_prefixes = ("user:", "role:", "tenant:")
        for entry in v:
            if not any(entry.startswith(p) for p in valid_prefixes):
                raise ValueError(
                    f"Invalid ACL entry '{entry}'. "
                    f"Must start with one of: {valid_prefixes}"
                )
            # Validate non-empty value after prefix
            prefix, _, value = entry.partition(":")
            if not value.strip():
                raise ValueError(
                    f"ACL entry '{entry}' has empty value after prefix"
                )
        return v

    @property
    def is_system_wide(self) -> bool:
        """True if this asset is shared across all tenants."""
        return self.tenant_id is None

    @property
    def is_tenant_scoped(self) -> bool:
        """True if this asset belongs to a specific tenant (S7-4)."""
        return self.tenant_id is not None

    @property
    def has_owner(self) -> bool:
        """True if this asset has an explicit user owner (S7-4)."""
        return self.owner_id is not None

    @property
    def is_shared(self) -> bool:
        """True if ACL grants access beyond the owner (S7-4)."""
        return len(self.acl) > 0

    @property
    def urn_string(self) -> str:
        """Shortcut to the full URN string."""
        return self.urn.urn

    def is_owned_by(self, user_id: str) -> bool:
        """Check if a user is the owner of this asset (S7-4)."""
        return self.owner_id is not None and self.owner_id == user_id

    def check_acl(self, user_id: str, roles: frozenset[str]) -> bool:
        """
        Check if a user matches any ACL entry (S7-4).

        Matches:
        - 'user:<user_id>' — exact user match
        - 'role:<role_name>' — any of the user's roles match
        - 'tenant:*' — always matches (tenant isolation already checked)

        Returns:
            True if the user matches at least one ACL entry.
        """
        for entry in self.acl:
            if entry == f"user:{user_id}":
                return True
            if entry == "tenant:*":
                return True
            if entry.startswith("role:"):
                role_name = entry[5:]  # len("role:") == 5
                if role_name in roles:
                    return True
        return False

    def __str__(self) -> str:
        return f"BIAsset({self.urn})"

    def __repr__(self) -> str:
        return f"BIAsset(urn='{self.urn}', name='{self.display_name}')"

    model_config = {"frozen": True}

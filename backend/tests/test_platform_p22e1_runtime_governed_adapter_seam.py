"""
P22-E1 Runtime Governed Action Adapter Seam -- NON-EXECUTING skeleton tests.

Backend-only, NON-EXECUTING skeleton of the runtime governed action adapter seam
defined by docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_CONTRACT.md
(P22-E0). The seam is the ONLY boundary a future real execution of a v0 action
may run through; this skeleton realizes the SHAPE only and runs nothing.

Coverage:
  - Adapter registry is allowlist-only: exactly the seven v0 actions, in order;
    resolution of an excluded / unknown / None / empty action is None; there is
    no generic dispatcher and no fallback adapter.
  - Every adapter is NON-EXECUTING / not_implemented; realizes_execution is False;
    the non-executing result never carries executed == True.
  - backup.check is an honest source_unknown / not_implemented slot: it never
    fabricates a healthy / known read and reads no unverified source.
  - Preflight gate reuses the P22-B precondition evaluator and is fail-closed:
    a fully valid binding passes (but still realizes no execution); a missing
    acknowledgement, a non-super_admin executor, an unknown action, a missing /
    invalid dry-run, an expired approval, a target mismatch, and an idempotency
    conflict each block. A passed verdict still has executed == False.
  - Idempotency is digest-only: new / replay / conflict classify correctly; the
    raw key is never accepted (only its digest).
  - Audit shape is templates of FIELD NAMES ONLY (before / after / failure /
    denial); it never carries a value, a secret, a digest-as-value, or
    executed == True.
  - No-execution invariants: an AST scan of EVERY p22 source file (the new seam
    modules included) proves no subprocess / os.system / os.popen / shell=True /
    eval / exec / harness / action-execution call token, and no p16 / subprocess /
    tenant / payment / product import; a raw-text scan of the new modules proves
    no invocation token; and the seam / adapters public API exposes no generic
    executor name.

The skeleton is import-tested only; it is not wired into any HTTP route, adds no
public execution entry point, and writes no audit event. Approval is not
execution and a passed preflight is not execution.
"""
import ast
import json
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- fixtures / shared state --------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_p22_state():
    """Reset the in-memory P22 store + the approval resolver before each test."""
    from api.v1.platform.p22 import services

    services.reset_store()
    services.reset_approval_resolver()
    yield
    services.reset_store()
    services.reset_approval_resolver()


# -- approval snapshot + resolver (deterministic, DB-free) --------------------


_APPROVALS: dict = {"by_id": {}}


def _resolver(approval_id):
    return _APPROVALS["by_id"].get(approval_id)


def _seed_approval(approval_id="ap-1", **overrides):
    """Seed a durable-approval snapshot with happy-path defaults."""
    from api.v1.platform.p22.services import ApprovalSnapshot

    base = dict(
        approval_id=approval_id,
        state="approved_execution_blocked",
        quorum_required=2,
        quorum_met=True,
        maker="maker-1",
        checker_ids=["checker-1", "checker-2"],
        source_status="known",
        action_type="support_mode.on",
        action_class="write",
        tenant_id=None,
        validation_status="valid",
        expires_at="2099-01-01T00:00:00+00:00",
    )
    base.update(overrides)
    snap = ApprovalSnapshot(**base)
    _APPROVALS["by_id"][approval_id] = snap
    return snap


@pytest.fixture(autouse=True)
def _reset_approvals():
    _APPROVALS["by_id"] = {}
    yield
    _APPROVALS["by_id"] = {}


def _install_resolver():
    from api.v1.platform.p22 import services

    services.set_approval_resolver(_resolver)


# -- helpers ------------------------------------------------------------------


async def _passed_dry_run(
    approval_id="ap-1",
    action_type="support_mode.on",
    actor="super-exec",
    **seed_over,
):
    """Seed a happy approval, run a real P22-B dry-run, return dry_run_id."""
    from api.v1.platform.p22 import services
    from api.v1.platform.p22.schemas import ExecutionDryRunRequest

    _install_resolver()
    _seed_approval(approval_id, action_type=action_type, **seed_over)
    tenant_id = seed_over.get("tenant_id")
    resp = await services.evaluate_dry_run(
        ExecutionDryRunRequest(
            durable_approval_id=approval_id,
            action_type=action_type,
            tenant_id=tenant_id,
            reason="planned support window",
            idempotency_key="idem-dry",
            execution_mode="sync",
        ),
        actor=actor,
        actor_role="super_admin",
        identity_context="identity_only",
    )
    assert resp.executable is True, resp.block_reasons
    return resp.dry_run_id


def _digest(value):
    from api.v1.platform.p22 import services

    return services._digest(value)


def _payload_digest(approval_id, action_type, tenant_id, requested_state, actor):
    from api.v1.platform.p22 import services

    return services._payload_digest(approval_id, action_type, tenant_id, requested_state, actor)


def _valid_request(approval_id="ap-1", action_type="support_mode.on", actor="super-exec",
                   dry_run_ref=None, **over):
    """A SeamAdapterRequest with every precondition satisfied."""
    from api.v1.platform.p22 import seam

    base = dict(
        durable_approval_id=approval_id,
        action_type=action_type,
        tenant_id=None,
        requested_state=None,
        dry_run_ref=dry_run_ref,
        execution_ack=True,
        idempotency_key_digest=_digest("idem-preflight-1"),
        payload_digest=_payload_digest(approval_id, action_type, None, None, actor),
        actor_id=actor,
        actor_role="super_admin",
        identity_context="identity_only",
        correlation_id="corr-preflight-1",
    )
    base.update(over)
    return seam.SeamAdapterRequest(**base)


# ============================================================================
# Adapter registry -- allowlist only, no generic dispatcher
# ============================================================================


def test_registry_lists_exactly_the_seven_allowlisted_actions_in_order():
    from api.v1.platform.p22 import adapters
    from api.v1.platform.p22.schemas import ALLOWED_ACTION_TYPES

    inv = adapters.adapter_registry_inventory()
    assert [d.action_type for d in inv] == list(ALLOWED_ACTION_TYPES)
    assert len(inv) == 7


def test_registry_resolves_allowlisted_actions_and_refuses_everything_else():
    from api.v1.platform.p22 import adapters

    assert adapters.resolve_adapter_descriptor("support_mode.on") is not None
    assert adapters.resolve_adapter_descriptor("backup.check") is not None
    # Excluded named actions, unknown strings, None, and empty all resolve to None.
    for bad in ("tenant.pause", "tenant.resume", "lifecycle.transition",
                "orders.refund", "payment.refund", "", None, "run_everything"):
        assert adapters.resolve_adapter_descriptor(bad) is None, bad
        assert adapters.is_registered_action(bad) is False, bad


def test_registry_has_no_generic_dispatcher_and_no_fallback():
    from api.v1.platform.p22 import adapters

    # The public API exposes no function that takes an arbitrary action string and
    # runs it; resolution is the only path and it is allowlist-only.
    public = [n for n in dir(adapters) if not n.startswith("_")]
    assert "dispatch" not in public
    assert "run" not in public
    assert "execute" not in public


# ============================================================================
# Every adapter is NON-EXECUTING / not_implemented
# ============================================================================


def test_every_descriptor_is_non_executing_and_not_implemented():
    from api.v1.platform.p22 import adapters

    for d in adapters.adapter_registry_inventory():
        assert d.realizes_execution is False
        assert d.adapter_result == "not_implemented"
        assert d.reads_business_data is False


def test_non_executing_result_never_claims_execution():
    from api.v1.platform.p22 import adapters

    for at in ("support_mode.on", "incident.flag_set", "provisioning.recheck",
               "backup.check", "backup.restore_test_request"):
        r = adapters.non_executing_adapter_result(at)
        assert r["registered"] is True
        assert r["realizes_execution"] is False
        assert r["executed"] is False
        assert r["result_state"] == "blocked"
        assert r["adapter_result"] == "not_implemented"


def test_non_executing_result_for_arbitrary_action_is_not_registered():
    from api.v1.platform.p22 import adapters

    r = adapters.non_executing_adapter_result("orders.refund")
    assert r["registered"] is False
    assert r["adapter_result"] == "not_registered"
    assert r["executed"] is False


# ============================================================================
# backup.check -- honest source_unknown / not_implemented slot
# ============================================================================


def test_backup_check_is_source_unknown_and_not_implemented():
    from api.v1.platform.p22 import adapters

    bc = adapters.resolve_adapter_descriptor("backup.check")
    assert bc is not None
    assert bc.source_status == "unknown"  # the P17 backup source is not wired
    assert bc.realizes_execution is False
    assert bc.adapter_result == "not_implemented"
    assert "not yet wired" in (bc.source_reason or "")


def test_backup_check_never_fabricates_a_healthy_source():
    from api.v1.platform.p22 import adapters

    # No adapter in the registry reports a known / healthy backup source.
    statuses = {d.action_type: d.source_status for d in adapters.adapter_registry_inventory()}
    for at, s in statuses.items():
        assert s == "unknown", (at, s)  # nothing is known in the P22-E1 skeleton
    assert statuses["backup.check"] != "known"


# ============================================================================
# Preflight gate -- fail-closed, reuses P22-B evaluator, never executes
# ============================================================================


@pytest.mark.asyncio
async def test_preflight_passes_on_a_fully_valid_binding_but_realizes_no_execution():
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run("ap-1", "support_mode.on")
    v = await seam.evaluate_preflight_gate(
        _valid_request("ap-1", "support_mode.on", dry_run_ref=dry)
    )
    assert v.verdict == "passed", v.block_reasons
    assert v.block_reasons == []
    assert v.registered is True
    # A passed preflight is NOT execution.
    assert v.realizes_execution is False
    assert v.realized_execution is False
    assert v.executed is False
    assert v.adapter_result == "not_implemented"
    assert v.idempotency_class == "new"
    # The passed shape names the before / after / failure / compensation templates.
    assert set(v.expected_audit_shape.keys()) == {
        "execution_started", "execution_succeeded", "execution_failed",
        "execution_compensation_recorded",
    }


@pytest.mark.asyncio
async def test_preflight_blocks_when_acknowledgement_missing():
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run()
    v = await seam.evaluate_preflight_gate(
        _valid_request(dry_run_ref=dry, execution_ack=False)
    )
    assert v.verdict == "blocked"
    assert "execution_ack_required" in v.block_reasons
    assert v.executed is False


@pytest.mark.asyncio
async def test_preflight_blocks_when_executor_not_identity_super_admin():
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run()
    v = await seam.evaluate_preflight_gate(
        _valid_request(dry_run_ref=dry, actor_role="support_operator")
    )
    assert v.verdict == "blocked"
    assert "executor_not_identity_super_admin" in v.block_reasons


@pytest.mark.asyncio
async def test_preflight_blocks_when_action_not_allowlisted():
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run("ap-1", "support_mode.on")
    # Same approval binding, but the request names an unknown action.
    req = _valid_request("ap-1", "orders.refund", dry_run_ref=dry)
    v = await seam.evaluate_preflight_gate(req)
    assert v.verdict == "blocked"
    assert "action_not_allowlisted" in v.block_reasons
    assert v.registered is False


@pytest.mark.asyncio
async def test_preflight_blocks_when_dry_run_missing_or_invalid():
    from api.v1.platform.p22 import seam

    _install_resolver()
    _seed_approval("ap-1")
    # No dry_run_ref at all.
    v1 = await seam.evaluate_preflight_gate(_valid_request(dry_run_ref=None))
    assert v1.verdict == "blocked"
    assert "dry_run_required" in v1.block_reasons
    # A dry_run_ref that does not resolve.
    v2 = await seam.evaluate_preflight_gate(_valid_request(dry_run_ref="does-not-exist"))
    assert v2.verdict == "blocked"
    assert "dry_run_invalid" in v2.block_reasons


@pytest.mark.asyncio
async def test_preflight_blocks_when_idempotency_digest_missing():
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run()
    v = await seam.evaluate_preflight_gate(
        _valid_request(dry_run_ref=dry, idempotency_key_digest=None)
    )
    assert v.verdict == "blocked"
    assert "idempotency_key_required" in v.block_reasons


@pytest.mark.asyncio
async def test_preflight_revalidates_approval_state_fail_closed():
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run("ap-1", "support_mode.on")
    # The approval expires / changes state between dry-run and preflight.
    _seed_approval("ap-1", state="expired")
    v = await seam.evaluate_preflight_gate(
        _valid_request("ap-1", "support_mode.on", dry_run_ref=dry)
    )
    assert v.verdict == "blocked"
    assert "approval_state_not_approved_execution_blocked" in v.block_reasons


@pytest.mark.asyncio
async def test_preflight_revalidates_target_tenant_binding():
    from api.v1.platform.p22 import seam

    # Dry-run passes with the approval scoped to tenant-A and the request at tenant-A.
    dry = await _passed_dry_run("ap-1", "support_mode.on", tenant_id="tenant-A")
    # The approval's target then moves to tenant-B between dry-run and preflight.
    _seed_approval("ap-1", action_type="support_mode.on", tenant_id="tenant-B")
    # The request still binds the dry-run (tenant-A), but the re-resolved approval
    # is now tenant-B -> target_mismatch_approval at execution time.
    v = await seam.evaluate_preflight_gate(
        _valid_request("ap-1", "support_mode.on", dry_run_ref=dry, tenant_id="tenant-A")
    )
    assert v.verdict == "blocked"
    assert "target_mismatch_approval" in v.block_reasons


@pytest.mark.asyncio
async def test_preflight_blocks_on_idempotency_conflict():
    from api.v1.platform.p22 import services, seam

    dry = await _passed_dry_run("ap-1", "support_mode.on")
    # Seed the recorded-request store with key K -> payload P1.
    key_digest = _digest("idem-conflict")
    services._EXEC_BY_KEY_DIGEST[key_digest] = "er-existing"
    services._EXEC_REQUESTS["er-existing"] = services._StoredExecutionRequest(
        execution_request_id="er-existing",
        payload_digest="payload-ONE",
    )
    # Same key K, but a DIFFERENT payload digest -> conflict.
    req = _valid_request("ap-1", "support_mode.on", dry_run_ref=dry,
                         idempotency_key_digest=key_digest, payload_digest="payload-TWO")
    v = await seam.evaluate_preflight_gate(req)
    assert v.verdict == "blocked"
    assert "idempotency_conflict" in v.block_reasons
    assert v.idempotency_class == "conflict"
    assert v.executed is False


@pytest.mark.asyncio
async def test_preflight_idempotency_replay_does_not_block_and_executes_nothing():
    from api.v1.platform.p22 import services, seam

    dry = await _passed_dry_run("ap-1", "support_mode.on")
    key_digest = _digest("idem-replay")
    services._EXEC_BY_KEY_DIGEST[key_digest] = "er-existing"
    services._EXEC_REQUESTS["er-existing"] = services._StoredExecutionRequest(
        execution_request_id="er-existing",
        payload_digest=_payload_digest("ap-1", "support_mode.on", None, None, "super-exec"),
    )
    req = _valid_request("ap-1", "support_mode.on", dry_run_ref=dry,
                         idempotency_key_digest=key_digest)
    v = await seam.evaluate_preflight_gate(req)
    assert v.idempotency_class == "replay"
    # A replay never applies a second state change and never executes.
    assert v.realized_execution is False
    assert v.executed is False


@pytest.mark.asyncio
async def test_backup_check_passes_preflight_only_as_a_non_executing_slot():
    """Even with a valid read approval, backup.check realizes no execution and
    reports an honest source_unknown adapter -- it never fabricates a read."""
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run("ap-r", "backup.check", action_class="read", source_status="known")
    v = await seam.evaluate_preflight_gate(
        _valid_request("ap-r", "backup.check", dry_run_ref=dry)
    )
    assert v.verdict == "passed", v.block_reasons
    assert v.adapter_result == "not_implemented"
    assert v.realized_execution is False
    assert v.executed is False
    # The adapter's honest source is unknown; the gate passing does not make it known.
    assert v.source_status == "unknown"


# ============================================================================
# Idempotency guard -- digest-only classify (raw key never accepted)
# ============================================================================


def test_classify_idempotency_new_replay_conflict():
    from api.v1.platform.p22 import services, seam

    services.reset_store()
    assert seam.classify_idempotency(None, None) == "new"
    assert seam.classify_idempotency("d-1", "p-1") == "new"
    services._EXEC_BY_KEY_DIGEST["d-1"] = "er-1"
    services._EXEC_REQUESTS["er-1"] = services._StoredExecutionRequest(
        execution_request_id="er-1", payload_digest="p-1"
    )
    assert seam.classify_idempotency("d-1", "p-1") == "replay"
    assert seam.classify_idempotency("d-1", "p-2") == "conflict"


def test_seam_request_never_carries_a_raw_idempotency_key():
    from api.v1.platform.p22 import seam

    req = seam.SeamAdapterRequest(idempotency_key_digest=_digest("raw-secret"))
    dump = json.dumps(req.model_dump(), default=str)
    # Only the digest is carried; the raw key is not a field and never appears.
    assert "raw-secret" not in dump
    assert "idempotency_key_digest" in dump


# ============================================================================
# Audit shape -- templates of field names only, no executed=True
# ============================================================================


def test_audit_shape_is_field_names_only_and_carries_no_value():
    from api.v1.platform.p22 import seam

    shape = seam.expected_seam_audit_shape("passed")
    blob = json.dumps(shape)
    # Field names only: no boolean value, no executed=true, no secret.
    assert "True" not in blob
    assert "False" not in blob
    assert "executed=true" not in blob.lower()
    for names in shape.values():
        assert names == list(seam.SEAM_AUDIT_FIELD_NAMES)
        assert "idempotency_key_digest" in names
        assert "reason_redacted" in names


@pytest.mark.asyncio
async def test_preflight_shape_does_not_leak_request_values():
    from api.v1.platform.p22 import seam

    dry = await _passed_dry_run()
    req = _valid_request(dry_run_ref=dry, correlation_id="SUPER-SECRET-CORR-XYZ")
    v = await seam.evaluate_preflight_gate(req)
    blob = json.dumps(v.expected_audit_shape)
    assert "SUPER-SECRET-CORR-XYZ" not in blob  # templates carry field names only


def test_non_execution_markers_are_false_everywhere():
    from api.v1.platform.p22 import adapters, seam

    assert adapters.ADAPTER_REALIZES_EXECUTION is False
    assert seam.SEAM_REALIZES_EXECUTION is False
    assert seam.SEAM_STORAGE_MODE == "memory"
    assert seam.SEAM_PHASE.startswith("P22-E1")


# ============================================================================
# No-execution invariants -- AST scan of EVERY p22 source file (new modules too)
# ============================================================================


def _all_p22_source_files():
    import api.v1.platform.p22 as pkg

    base = os.path.dirname(pkg.__file__)
    for name in sorted(os.listdir(base)):
        if name.endswith(".py"):
            path = os.path.join(base, name)
            with open(path, "r", encoding="utf-8") as fh:
                yield path, fh.read()


def _ast_dotted(node):
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def test_no_subprocess_shell_or_execution_call_tokens_in_any_p22_source():
    """AST scan of every p22 *.py (seam + adapters included): no code-execution
    call token, no shell=True, no harness / action-execution attribute call."""
    forbidden_bare = {"eval", "exec", "system", "popen", "run"}
    forbidden_os_attrs = {"system", "popen", "execv", "execve"}
    forbidden_attr_substrings = (
        "harness", "execute_action", "run_action", "dispatch_action",
        "drain_queue", "start_worker", "invoke_harness",
    )
    for path, src in _all_p22_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id not in forbidden_bare, (
                        f"forbidden bare call {f.id!r} in {os.path.basename(path)}"
                    )
                elif isinstance(f, ast.Attribute):
                    dotted = _ast_dotted(f.value)
                    assert not dotted.startswith("subprocess"), (
                        f"forbidden subprocess call in {path}"
                    )
                    assert not (dotted == "os" and f.attr in forbidden_os_attrs), (
                        f"forbidden os.{f.attr} call in {path}"
                    )
                    low = f.attr.lower()
                    assert not any(s in low for s in forbidden_attr_substrings), (
                        f"forbidden execution attr {f.attr!r} in {os.path.basename(path)}"
                    )
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                            and kw.value.value is True:
                        raise AssertionError(f"shell=True forbidden in {path}")


def test_no_forbidden_imports_in_any_p22_source():
    """No p22 source imports subprocess / p16 / product / tenant-business modules."""
    forbidden_import_substrings = (
        "subprocess", "p16", "product", "order", "payment", "invoice",
        "customer", "inventory", "ledger", "billing",
    )
    for _path, src in _all_p22_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
            for m in mods:
                low = m.lower()
                for tok in forbidden_import_substrings:
                    assert tok not in low, f"forbidden import {m!r} in p22 source"


def test_new_seam_modules_have_no_invocation_token_in_text():
    """Raw-text proof on the new modules: no external-process / shell / eval /
    SQL / P16-runtime invocation token appears, even as a literal."""
    import api.v1.platform.p22 as pkg

    base = os.path.dirname(pkg.__file__)
    tokens = (
        "subprocess", "os.system", "os.popen", "os.execv", "os.execve",
        "shell=True", "shell= True", "eval(", "exec(", "import p16", "from p16",
        ".execute(", "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ",
        "ALTER ", "TRUNCATE ",
    )
    for name in ("seam.py", "adapters.py"):
        with open(os.path.join(base, name), "r", encoding="utf-8") as fh:
            text = fh.read()
        for tok in tokens:
            assert tok not in text, f"forbidden token {tok!r} in {name}"


def test_seam_and_adapters_expose_no_generic_executor_name():
    """The seam / adapters public API exposes no execute / run / dispatch /
    invoke / start_worker name -- there is no generic executor surface."""
    from api.v1.platform.p22 import adapters, seam

    forbidden = ("execute", "execute_action", "run_action", "dispatch", "drain",
                 "invoke", "invoke_harness", "start_worker", "run")
    for mod in (adapters, seam):
        public = {n for n in dir(mod) if not n.startswith("_")}
        for name in forbidden:
            assert name not in public, f"forbidden executor name {name!r} in {mod.__name__}"


def test_seam_reuses_p22b_precondition_helpers_not_a_copy():
    """The preflight gate reuses the P22-B precondition evaluator symbols rather
    than re-implementing execution semantics (P22-E0 9.1)."""
    from api.v1.platform.p22 import seam

    src = inspect_getsource(seam.evaluate_preflight_gate)
    # It delegates executor / classification / approval evaluation to P22-B.
    assert "_executor_block_reason" in src
    assert "_classify_action" in src
    assert "_check_approval_preconditions" in src
    assert "_resolve_approval" in src


def inspect_getsource(func):
    import inspect

    return inspect.getsource(func)

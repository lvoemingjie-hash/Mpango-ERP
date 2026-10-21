"""Offline schema-source checks; these do not replace PG migration/parity tests."""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT/'alembic/versions/043_staff_authority_and_credentials.py'
BOOTSTRAP = ROOT/'scripts/bootstrap_tenant_schema.py'


def literal_assignment(tree, name):
    return next(ast.literal_eval(node.value) for node in ast.walk(tree)
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets))


def test_migration_and_independent_bootstrap_declare_identical_tenant_ddl():
    migration = ast.parse(MIGRATION.read_text())
    bootstrap = ast.parse(BOOTSTRAP.read_text())
    function = next(node for node in bootstrap.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == '_reconcile_staff_authority')
    normalize = lambda statements: tuple(re.sub(r'\s+', ' ', value).strip() for value in statements)
    assert normalize(literal_assignment(migration, 'TENANT_DDL')) == normalize(literal_assignment(function, 'statements'))


def test_migration_revision_is_exact_successor_and_has_no_runtime_service_import():
    tree = ast.parse(MIGRATION.read_text())
    assert literal_assignment(tree, 'revision') == '043_staff_authority_and_credentials'
    assert literal_assignment(tree, 'down_revision') == '042_order_negotiation_proposals'
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or '').startswith(('models', 'services', 'scripts'))


def test_migration_does_not_claim_or_activate_historical_owner():
    source = MIGRATION.read_text()
    assert 'INSERT INTO {q}.staff_authority (tenant_id,registration_id)' in source
    assert 'owner_email' not in source
    assert "SET is_active" not in source
    assert 'owner_user_id=:u' not in source
    assert 'staff_memberships' in source
    assert 'adjustment_requests' not in source
    assert 'stock_revision' not in source


def test_m1_authority_does_not_require_runtime_public_references():
    for path in (MIGRATION, BOOTSTRAP):
        source = path.read_text()
        assert 'registration_id UUID REFERENCES public.tenant_registrations' not in source
    migration = ast.parse(MIGRATION.read_text())
    assert 'REFERENCES {q}.users(id) ON DELETE RESTRICT' in literal_assignment(migration, 'TENANT_DDL')[0]


def test_audit_ddl_is_append_only_and_has_no_soft_delete():
    migration = ast.parse(MIGRATION.read_text())
    public = literal_assignment(migration, 'PUBLIC_DDL')
    audit_ddl = next(sql for sql in public if sql.startswith('CREATE TABLE public.staff_stock_audit_events'))
    assert 'is_deleted' not in audit_ddl and 'deleted_at' not in audit_ddl
    assert any('BEFORE UPDATE OR DELETE ON public.staff_stock_audit_events' in sql for sql in public)
    assert any('REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER' in sql for sql in public)


def test_repeated_grants_and_audit_revocation_share_one_transaction():
    tree = ast.parse((ROOT/'scripts/provision_runtime_db_roles.py').read_text())
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                    and n.name == 'apply_minimum_grants')
    protected = next(n for n in ast.walk(function) if isinstance(n, ast.AsyncWith)
                     and 'migrate.transaction()' in ast.unparse(n.items[0].context_expr))
    source = ast.unparse(protected)
    assert 'for sql in statements' in source
    assert 'REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER' in source
    assert 'staff_stock_audit_events' in source


def test_verified_owner_is_immutable_and_downgrade_refuses():
    migration = ast.parse(MIGRATION.read_text())
    tenant = literal_assignment(migration, 'TENANT_DDL')
    assert any("OLD.state='verified'" in sql and "RAISE EXCEPTION 'OWNER_PROTECTED'" in sql for sql in tenant)
    function = next(n for n in migration.body if isinstance(n, ast.FunctionDef) and n.name == 'downgrade')
    assert isinstance(function.body[0], ast.Raise)

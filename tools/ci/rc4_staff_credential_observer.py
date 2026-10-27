"""Bounded, call-window-only observations; never a credential decision."""
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
import sys
from types import CodeType, FunctionType, ModuleType

import pytest

_SOURCE = 'backend/services/staff_credential_service.py'
_SOURCE_SHA256 = 'a0fbaff8485305948639f02b2b36fc8f1c9c8180a7124fa5dc20b8a0a3b8ac7c'
_MODULE = 'tests/test_dc12r1_j1_h2_b_r3_r1_user_role_assignment_async_serialization.py'
_NAMES = frozenset({
    'test_t1_put_roles_200_full_scalars_and_admin_role',
    'test_t2_serialization_zero_implicit_sql_no_missing_greenlet',
    'test_t3_fresh_session_binding_persisted_exactly_once',
    'test_t4_invalid_role_exact_400_and_zero_partial_binding',
    'test_t5_unknown_user_exact_404_user_not_found',
    'test_t6_dual_tenant_same_email_isolated_role_assignment',
    'test_t7_real_permission_chain_and_denial',
    'test_t8_rollback_leaves_zero_user_roles_residue',
    'test_t9_final_residue_zero',
})
PROPERTY_NAME = 'rc4_staff_observation_v1'


def _is_target(nodeid):
    return type(nodeid) is str and nodeid in {_MODULE + '::' + name for name in _NAMES}


def _bound_service():
    # Do not import product/Settings/engines at collection or even to fill a
    # missing module: absence is a GAP, not a reason to change initialization.
    module = sys.modules.get('services.staff_credential_service')
    if type(module) is not ModuleType:
        raise ValueError('SOURCE_BINDING_REFUSED')
    expected = Path(__file__).resolve().parents[2] / _SOURCE
    actual = vars(module).get('__file__')
    original = vars(module).get('proof_failed')
    raw = expected.read_bytes()
    if len(raw) != 8596 or sha256(raw).hexdigest() != _SOURCE_SHA256:
        raise ValueError('SOURCE_BINDING_REFUSED')
    compiled = compile(raw, str(expected), 'exec', dont_inherit=True)
    definitions = [c for c in compiled.co_consts if type(c) is CodeType and c.co_name == 'proof_failed']
    if (type(actual) is not str or expected.is_symlink()
            or not stat.S_ISREG(expected.lstat().st_mode)
            or stat.S_IMODE(expected.lstat().st_mode) & 0o111
            or Path(actual).resolve(strict=True) != expected
            or sha256(raw).hexdigest() != _SOURCE_SHA256
            or type(original) is not FunctionType or original.__globals__ is not vars(module)
            or Path(original.__code__.co_filename).resolve(strict=True) != expected
            or len(definitions) != 1 or original.__code__ != definitions[0]):
        raise ValueError('SOURCE_BINDING_REFUSED')
    return module, original, expected


def _engine_events():
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    return event, Engine


class _Observation:
    def __init__(self, item):
        self.item = item
        self.module = self.original = self.wrapper = None
        self.event = self.engine = self.source = None
        self.listening = self.enabled = self.restored = False
        self.events = []
        self.errors = []
        self.clipped = False

    def _error(self, code):
        if code not in self.errors:
            self.errors.append(code)

    def _append(self, event):
        if len(self.events) < 16:
            self.events.append(event)
        else:
            self.clipped = True

    def _proof(self, frame):
        site, line = 'UNKNOWN', None
        if (frame.f_globals is vars(self.module)
                and Path(frame.f_code.co_filename).resolve(strict=True) == self.source):
            site, line = _SOURCE, frame.f_lineno
        else:
            self._error('SITE_UNKNOWN')
        local = frame.f_locals
        schema = local.get('schema')
        schema_hash = sha256(schema.encode('ascii')).hexdigest() if (
            type(schema) is str and re.fullmatch(r't_[0-9a-f]{32}', schema)) else None
        def count(value):
            return len(value) if type(value) in (list, tuple) else None
        self._append({'kind': 'PROOF_FAILED', 'site': site, 'line': line,
                      'schema_sha256': schema_hash, 'active_count': count(local.get('active')),
                      'other_copy_count': count(local.get('rows'))})

    def _sql_error(self, context):
        try:
            exc = context.original_exception
            state = getattr(exc, 'sqlstate', None)
            if type(state) is not str:
                state = getattr(exc, 'pgcode', None)
            if type(state) is not str or re.fullmatch(r'[0-9A-Z]{5}', state) is None:
                state = None
                self._error('SQLSTATE_UNKNOWN')
            statement = context.statement
            is_copy = type(statement) is str and statement.startswith(
                'SELECT id,password_hash,is_active,is_deleted FROM ')
            self._append({'kind': 'SQL_ERROR', 'sqlstate': state, 'staff_copy_query': is_copy})
        except Exception:
            self._error('CALLBACK_ERROR')
        # No retval listener, no replacement exception, no SQL or retry.

    def start(self):
        try:
            self.module, self.original, self.source = _bound_service()
            self.event, self.engine = _engine_events()
            def observed(*args, **kwargs):
                try:
                    self._proof(sys._getframe(1))
                except Exception:
                    self._error('CALLBACK_ERROR')
                return self.original(*args, **kwargs)
            self.wrapper = observed
            self.module.proof_failed = self.wrapper
            self.listening = True
            self.event.listen(self.engine, 'handle_error', self._sql_error)
            self.enabled = True
        except Exception:
            self._error('INSTALL_ERROR')

    def stop(self):
        restored = True
        try:
            if self.module is not None and self.wrapper is not None:
                self.module.proof_failed = self.original
        except Exception:
            restored = False
            self._error('RESTORE_ERROR')
        try:
            if self.listening:
                self.event.remove(self.engine, 'handle_error', self._sql_error)
                self.listening = False
        except Exception:
            restored = False
            self._error('RESTORE_ERROR')
        self.restored = restored and self.enabled

    def publish(self):
        complete = self.enabled and self.restored and not self.errors
        data = {'version': 1, 'enabled': self.enabled, 'restored': self.restored,
                'status': ('CLIPPED' if self.clipped else 'COMPLETE') if complete else 'GAP', 'errors': self.errors,
                'events': self.events, 'clipped': self.clipped}
        try:
            self.item.user_properties.append((PROPERTY_NAME, json.dumps(data, sort_keys=True)))
        except Exception:
            # Missing property is an explicit downstream observation GAP,
            # never a reason to replace the test's result or exception.
            return False
        return True


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if not _is_target(item.nodeid):
        yield
        return
    observation = _Observation(item)
    try:
        observation.start()
        yield
    finally:
        observation.stop()
        observation.publish()

"""Real task credentials and TCP clients; no ASGI transport or auth override."""
import json
import sys
import uuid

import pytest_asyncio

from tests.s2_reorder.support import TASK_ROOT


def pytest_configure(config):
    """Reject an incomplete attachment during collection, never skip to green."""
    sys.path.insert(0, str(TASK_ROOT / 'work'))
    from runtime_inputs import load_accounts, load_runtime
    from s2_fixture_api import FixtureAPI
    load_runtime()
    load_accounts()
    assert callable(FixtureAPI), 'S2_TASK_FIXTURE_IMPORT_REQUIRED'


@pytest_asyncio.fixture
async def live(request):
    sys.path.insert(0, str(TASK_ROOT / 'work'))
    from s2_fixture_api import FixtureAPI
    country = getattr(request, 'param', 'KE')
    async with FixtureAPI(country) as fixture:
        fixture.evidence_suffix = uuid.uuid4().hex[:10]
        yield fixture
        directory = TASK_ROOT / 'private' / 'backend-http-calls'
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (request.node.name.replace('/', '_') + '-' + uuid.uuid4().hex[:8] + '.json')
        path.write_text(json.dumps(fixture.calls, indent=2) + '\n')
        path.chmod(0o600)

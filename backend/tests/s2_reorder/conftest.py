"""Real task credentials and TCP clients; no ASGI transport or auth override."""
import json
import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

TASK_ROOT = Path(os.environ.get('S2_TASK_ROOT', Path(__file__).resolve().parents[4]))


@pytest_asyncio.fixture
async def live(request):
    if not (TASK_ROOT / 'work' / 's2_fixture_api.py').is_file():
        pytest.skip('S2_TASK_RUNTIME_CAPSULE_NOT_CONFIGURED: task-owned TCP/PG inputs are required')
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

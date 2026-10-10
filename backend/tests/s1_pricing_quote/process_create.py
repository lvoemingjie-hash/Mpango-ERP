"""One task HTTP request in a fresh OS process; secrets enter only via stdin/env."""
import asyncio
import json
import sys
from unittest.mock import patch


async def main():
    from api.app import configure_app
    from auth.strategies.jwt import JwtAuthStrategy
    from core.config import get_settings
    from core.error_codes import register_exception_handlers
    from database.session import async_engine
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    app = FastAPI()
    with patch('auth.factory.get_auth_strategy', return_value=JwtAuthStrategy()):
        configure_app(app, get_settings())
    register_exception_handlers(app)
    print('S1_PROCESS_READY', flush=True)
    payload = json.loads(await asyncio.to_thread(sys.stdin.readline))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as http:
        result = await http.post('/api/v1/orders', json=payload['body'], headers={
            'Authorization': 'Bearer ' + payload['token'],
            'X-Idempotency-Key': payload['key'],
        })
        body = result.json()
        print('S1_RESULT ' + json.dumps({'status': result.status_code,
              'id': (body.get('data') or {}).get('id'), 'code': body.get('code')}), flush=True)
    await async_engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

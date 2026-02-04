import os
import unittest

from fastapi.testclient import TestClient

from fastapi import FastAPI, Request

from api.context.auth import get_auth_context
from api.context.tenant import get_tenant_context
from api.middleware.auth import AuthenticationMiddleware
from auth.factory import get_auth_strategy


class TestTestModeAuthBypass(unittest.TestCase):
    def test_payments_endpoint_callable_without_jwt_when_test_mode(self):
        os.environ["MPANGO_ENV"] = "test"

        app = FastAPI()
        app.add_middleware(AuthenticationMiddleware, strategy=get_auth_strategy())

        @app.get("/whoami")
        async def _whoami(request: Request):
            auth_ctx = get_auth_context(request)
            return {"user_id": auth_ctx.token.user_id}

        @app.get("/protected")
        async def _protected(request: Request):
            tenant_ctx = get_tenant_context(request)
            user_permissions = set()
            for role in tenant_ctx.user.roles:
                for perm in role.permissions:
                    user_permissions.add(perm.code)
            return {"ok": "payments:create" in user_permissions}

        client = TestClient(app)

        resp = client.get("/protected")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])


if __name__ == "__main__":
    unittest.main()

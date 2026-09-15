"""Published generator (writes the evidence JSON to stdout; redirect it)

Published generator (see the R3 evidence README).

Same logic as the task-local script that produced the R3 evidence, with
absolute paths replaced by environment lookups so it runs from a checkout:

  KIMI_SMTP_BACKEND_DIR     backend/ directory of the checkout (required)
  KIMI_SMTP_EVIDENCE_DIR    where evidence files are written (default .)
  python                    sys.executable is used for subprocesses
"""
import os
import sys

BACKEND = os.environ["KIMI_SMTP_BACKEND_DIR"]
WORKTREE = os.path.dirname(os.path.abspath(BACKEND))
PYTHON = sys.executable
SCRATCH = os.environ.get("KIMI_SMTP_EVIDENCE_DIR") or os.getcwd()


import asyncio
import json
import os
import sys

sys.path.insert(0, BACKEND)

import asyncpg  # noqa: E402

URL_ENV = "KIMI_SMTP_TASK_DATABASE_URL"


async def main() -> None:
    url = (os.environ.get(URL_ENV) or "").strip()
    if not url:
        raise SystemExit(f"{URL_ENV} must be set")
    dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    database = dsn.rsplit("/", 1)[-1]
    conn = await asyncpg.connect(dsn)
    try:
        evidence: dict = {"database": database, "connected_database": await conn.fetchval("SELECT current_database()")}
        evidence["registrations_matching_prefix"] = await conn.fetchval(
            "SELECT count(*) FROM public.tenant_registrations WHERE owner_email LIKE 'kimi\\_smtp\\_%'"
        )
        evidence["verification_tokens_for_prefix"] = await conn.fetchval(
            "SELECT count(*) FROM public.email_verification_tokens evt JOIN public.tenant_registrations tr "
            "ON tr.id = evt.registration_id WHERE tr.owner_email LIKE 'kimi\\_smtp\\_%'"
        )
        evidence["status_tokens_for_prefix"] = await conn.fetchval(
            "SELECT count(*) FROM public.onboarding_status_tokens ost JOIN public.tenant_registrations tr "
            "ON tr.id = ost.registration_id WHERE tr.owner_email LIKE 'kimi\\_smtp\\_%'"
        )
        evidence["setup_tokens_for_prefix"] = await conn.fetchval(
            "SELECT count(*) FROM public.owner_credential_setup_tokens oct JOIN public.tenant_registrations tr "
            "ON tr.id = oct.registration_id WHERE tr.owner_email LIKE 'kimi\\_smtp\\_%'"
        )
        evidence["wholesalers_without_registration"] = await conn.fetchval(
            "SELECT count(*) FROM public.wholesalers w WHERE NOT EXISTS "
            "(SELECT 1 FROM public.tenant_registrations tr WHERE tr.wholesaler_id = w.id)"
        )
        schemas = await conn.fetch(
            "SELECT nspname FROM pg_namespace WHERE nspname ~ '^t_[0-9a-f]{32}$' ORDER BY 1"
        )
        evidence["task_shaped_tenant_schemas"] = [row["nspname"] for row in schemas]
        evidence["residue_free"] = (
            evidence["registrations_matching_prefix"] == 0
            and evidence["verification_tokens_for_prefix"] == 0
            and evidence["status_tokens_for_prefix"] == 0
            and evidence["setup_tokens_for_prefix"] == 0
            and evidence["task_shaped_tenant_schemas"] == []
        )
        print(json.dumps(evidence, indent=2))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

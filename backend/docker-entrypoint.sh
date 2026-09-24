#!/bin/sh
# Mpango ERP backend RUNTIME entrypoint.
#
# R1-R4 (CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R4-BOUNDED-RUNTIME-CONTRACT-CORRECTION-2026-09-19):
# this entrypoint performs ZERO migration, provisioning, grant, public DDL or
# tenant-bootstrap writes.  The container receives ONLY the runtime-role
# DATABASE_URL (container context).  Readiness is delegated to the extracted
# helper scripts/runtime_readiness_gate.py, which verifies -- strictly
# read-only, both accepted URL schemes, refusal reasons scoped per attempt --
# that the five-stage setup.sh sequence completed:
#
#   1 provision (admin) -> 2 alembic through 039 (migration authority)
#   -> 3 minimum grants -> 4 read-only verify -> 5 tenant bootstrap (runtime)
#
# Started early, the gate names the missing contract and the container never
# becomes a partially prepared traffic-ready backend.

set -e

echo "=== Mpango ERP Backend Startup (runtime only) ==="

python - <<'PYEOF'
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from scripts.runtime_readiness_gate import main

sys.exit(main())
PYEOF

echo "Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000

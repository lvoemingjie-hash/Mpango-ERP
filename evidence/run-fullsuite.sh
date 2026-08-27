#!/bin/bash
# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-V2 authoritative full backend suite launcher
# Single run. No retries. JUnit + raw log archived.
set -u
cd /tmp/dc12r1-v2-worktree/backend
source /tmp/dc12r1-v2-venv/bin/activate
export DATABASE_URL="postgresql://mpango_test:***@localhost:15432/mpango_erp_test"
export TEST_DATABASE_URL="postgresql://mpango_test:***@localhost:15432/mpango_erp_test"
export REDIS_URL="redis://localhost:16379/0"
export PW1R3_TEST_REDIS_URL="redis://localhost:16379/15"
export SECRET_KEY=***SANITIZED***
export REPORTING_USER_PASSWORD=***SANITIZED***
export MPANGO_ENV="test"
export PYTHONUNBUFFERED=1
echo "=== AUTHORITATIVE FULL SUITE START $(date -Is) ==="
echo "CANDIDATE=$(git rev-parse HEAD)"
python3 -m pytest tests/ -q --tb=line \
  --junitxml=/tmp/dc12r1-v2-evidence/fullsuite-authoritative.xml \
  > /tmp/dc12r1-v2-evidence/fullsuite-authoritative.log 2>&1
rc=$?
echo "=== AUTHORITATIVE FULL SUITE END $(date -Is) exit=$rc ==="
tail -5 /tmp/dc12r1-v2-evidence/fullsuite-authoritative.log

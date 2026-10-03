#!/bin/bash
# Test login endpoint
for name in MPANGO_SMOKE_LOGIN_URL MPANGO_TEST_ADMIN_PASSWORD; do
    if [[ -z "${!name:-}" || -z "${!name//[[:space:]]/}" ]]; then
        printf 'SMOKE_INPUT_REQUIRED: %s\n' "$name" >&2
        exit 2
    fi
done
python3 -c 'import json,os; print(json.dumps(dict(email="admin@mpango.demo",password=os.environ["MPANGO_TEST_ADMIN_PASSWORD"])))' | curl -s -X POST "$MPANGO_SMOKE_LOGIN_URL" \
  -H 'Content-Type: application/json' \
  -d @-
echo ""

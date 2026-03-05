#!/bin/bash
# Test login endpoint
curl -s -X POST http://localhost/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@test.com","password":"testpass123"}'
echo ""

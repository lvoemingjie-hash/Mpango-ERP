#!/bin/bash
# Test login endpoint
curl -s -X POST http://localhost/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@mpango.demo","password":"DemoAdmin2026!"}'
echo ""

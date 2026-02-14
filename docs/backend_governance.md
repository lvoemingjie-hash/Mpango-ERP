# Backend Governance Rules

## Rule 1: The "Manageable Entity" Standard
Any entity that appears in a Frontend Sidebar/Menu, Dropdown (>1 items), or is a Core Configuration MUST have full CRUD endpoints (List, Create, Update, Delete) before "Phase Freeze".

## Rule 2: The "API Completeness Review" Protocol
Before Track C (Frontend) starts any module, a "Frontend-First" review must occur: Map every UI page/modal to specific API endpoints (List/Create/Update/Delete) and verify Permissions, Uniqueness Checks, and Error Codes.

# SC-002: Create User

## Scenario ID
`SC-002`

## Feature
**User Management with RBAC**

## User Story
```
As a Wholesaler Admin
I want to create new users in my tenant
So that my team members can access the ERP system with appropriate permissions
```

## Authority
- **L0**: `RBAC Matrix (MVP).md` - users:create permission
- **L0**: `Database Contract.md` - users table schema
- **L0**: `Multi-Tenancy Spec (MVP).md` - tenant-scoped data

---

## Scenario: Admin Creates a New Sales User

### Given (前置条件)
```gherkin
Given I am logged in as "admin@acme.com" with role "admin"
And my JWT contains tenant_schema "t_acme01"
And the role "sales" exists in the tenant schema
```

### When (触发动作)
```gherkin
When I send POST /api/v1/users with:
  {
    "email": "sales@acme.com",
    "password": "Sales123!",
    "full_name": "Sales Person"
  }
And Authorization header is "Bearer <valid_admin_token>"
```

### Then (预期结果)
```gherkin
Then the response status code is 200
And the response body contains:
  {
    "id": "<UUID>",
    "email": "sales@acme.com",
    "full_name": "Sales Person",
    "is_active": true,
    "created_at": "<timestamp>",
    "updated_at": "<timestamp>"
  }
And the response does NOT contain "password_hash"
And a new user record exists in tenant schema with email "sales@acme.com"
```

---


## Scenario: Create User Without Permission

### Given
```gherkin
Given I am logged in as "sales@acme.com" with role "sales"
And the "sales" role does NOT have "users:create" permission
```

### When
```gherkin
When I send POST /api/v1/users with:
  {
    "email": "newuser@acme.com",
    "password": "NewUser123!",
    "full_name": "New User"
  }
```

### Then
```gherkin
Then the response status code is 403
And the response body contains:
  {
    "detail": "Permission denied"
  }
And no new user is created
```

---

## Scenario: Create User with Duplicate Email

### Given
```gherkin
Given I am logged in as admin
And a user with email "existing@acme.com" already exists
```

### When
```gherkin
When I send POST /api/v1/users with:
  {
    "email": "existing@acme.com",
    "password": "Password123!",
    "full_name": "Duplicate User"
  }
```

### Then
```gherkin
Then the response status code is 400
And the response body contains:
  {
    "detail": "Email already registered"
  }
```

---

## Scenario: Create User Without Authentication

### Given
```gherkin
Given I am not authenticated (no Authorization header)
```

### When
```gherkin
When I send POST /api/v1/users with:
  {
    "email": "newuser@acme.com",
    "password": "Password123!"
  }
```

### Then
```gherkin
Then the response status code is 401
And the response body contains:
  {
    "detail": "Could not validate credentials"
  }
```

---

## Implementation Checklist

### Backend AI
- [ ] Implement `POST /api/v1/users` endpoint
- [ ] Require `users:create` permission via `require_permission("users:create")`
- [ ] Hash password before storing
- [ ] Check for duplicate email
- [ ] Create user in tenant schema (via search_path)
- [ ] Return UserRead schema (exclude password_hash)

### Frontend AI
- [ ] Implement user creation form
- [ ] Validate email format and password strength
- [ ] Display success/error messages
- [ ] Refresh user list after creation

---

## Permission Requirements
| Role | Can Execute | Reason |
|------|-------------|--------|
| admin | ✅ Yes | Has `users:create` permission |
| sales | ❌ No | Does not have `users:create` |
| warehouse | ❌ No | Does not have `users:create` |
| finance | ❌ No | Does not have `users:create` |

---

**Created by:** Architect AI
**Date:** 2025-01-09
**Status:** 📝 Defined

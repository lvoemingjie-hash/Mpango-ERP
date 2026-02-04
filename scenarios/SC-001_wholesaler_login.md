# SC-001: Wholesaler Login

## Scenario ID
`SC-001`

## Feature
**Multi-Tenant Authentication**

## User Story
```
As a Wholesaler Admin
I want to login to my tenant's ERP system
So that I can manage my wholesale business operations
```

## Authority
- **L0**: `Multi-Tenancy Spec (MVP).md` - Section 4.1 Login Flow
- **L0**: `RBAC Matrix (MVP).md` - admin role permissions

---

## Scenario: Successful Wholesaler Admin Login

### Given (前置条件)
```gherkin
Given a wholesaler exists in public.wholesalers with:
  | field      | value       |
  | code       | "ACME01"    |
  | name       | "ACME Corp" |
  | plan_type  | "premium"   |

And the tenant schema "t_<wholesaler_id_without_dashes>" exists

And a user exists in the tenant schema with:
  | field         | value                |
  | email         | "admin@acme.com"     |
  | password_hash | bcrypt("Admin123!")  |
  | is_active     | true                 |
  | is_deleted    | false                |

And the user has role "admin" assigned
```

### When (触发动作)
```gherkin
When the client sends POST /api/v1/auth/login with:
  {
    "tenant_code": "ACME01",
    "email": "admin@acme.com",
    "password": "Admin123!"
  }
```

### Then (预期结果)
```gherkin
Then the response status code is 200

And the response body contains:
  {
    "access_token": "<non-empty JWT>",
    "refresh_token": "<non-empty JWT>",
    "token_type": "bearer",
    "user_id": "<UUID>",
    "tenant_id": "<UUID>",
    "tenant_schema": "t_<uuid_without_dashes>"
  }

And the access_token JWT payload contains:
  {
    "user_id": "<same as response.user_id>",
    "tenant_id": "<same as response.tenant_id>",
    "tenant_schema": "<same as response.tenant_schema>",
    "exp": "<future timestamp>"
  }
```

---

## Scenario: Login with Invalid Tenant Code

### Given
```gherkin
Given no wholesaler exists with code "INVALID"
```

### When
```gherkin
When the client sends POST /api/v1/auth/login with:
  {
    "tenant_code": "INVALID",
    "email": "admin@acme.com",
    "password": "Admin123!"
  }
```

### Then
```gherkin
Then the response status code is 404
And the response body contains:
  {
    "detail": "Tenant not found"
  }
```

---

## Scenario: Login with Invalid Credentials

### Given
```gherkin
Given a wholesaler exists with code "ACME01"
And a user exists with email "admin@acme.com" and password "Admin123!"
```

### When
```gherkin
When the client sends POST /api/v1/auth/login with:
  {
    "tenant_code": "ACME01",
    "email": "admin@acme.com",
    "password": "WrongPassword!"
  }
```

### Then
```gherkin
Then the response status code is 401
And the response body contains:
  {
    "detail": "Invalid credentials"
  }
```

---

## Scenario: Login with Inactive User

### Given
```gherkin
Given a wholesaler exists with code "ACME01"
And a user exists with:
  | email     | "inactive@acme.com" |
  | is_active | false               |
```

### When
```gherkin
When the client sends POST /api/v1/auth/login with:
  {
    "tenant_code": "ACME01",
    "email": "inactive@acme.com",
    "password": "Admin123!"
  }
```

### Then
```gherkin
Then the response status code is 400
And the response body contains:
  {
    "detail": "Inactive user"
  }
```

---

## Implementation Checklist

### Backend AI
- [ ] Implement `POST /api/v1/auth/login` endpoint
- [ ] Query `public.wholesalers` by `tenant_code`
- [ ] Derive `tenant_schema` from `wholesaler.id`
- [ ] Set `search_path` to tenant schema
- [ ] Authenticate user in tenant schema
- [ ] Generate JWT with `tenant_id`, `tenant_schema`, `user_id`
- [ ] Return proper error codes for each failure case

### Frontend AI
- [ ] Implement login form with `tenant_code`, `email`, `password` fields
- [ ] Store tokens in localStorage
- [ ] Redirect to dashboard on success
- [ ] Display error messages on failure

### Ops AI
- [ ] Ensure PostgreSQL allows schema switching
- [ ] Configure JWT secret in environment

---

## Test Data Requirements
```sql
-- public schema
INSERT INTO public.wholesalers (id, code, name, plan_type)
VALUES ('11111111-1111-1111-1111-111111111111', 'ACME01', 'ACME Corp', 'premium');

-- tenant schema (t_11111111111111111111111111111111)
INSERT INTO users (id, email, password_hash, full_name, is_active)
VALUES ('22222222-2222-2222-2222-222222222222', 'admin@acme.com', '<bcrypt_hash>', 'Admin User', true);

INSERT INTO roles (id, name) VALUES ('33333333-3333-3333-3333-333333333333', 'admin');

INSERT INTO user_roles (user_id, role_id)
VALUES ('22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333');
```

---

**Created by:** Architect AI
**Date:** 2025-01-09
**Status:** 📝 Defined

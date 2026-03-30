# 2026-03-05 — Frontend Two-Phase Auth Implementation

**Role:** Senior Frontend Engineer
**Status:** ✅ Completed
**Context:** Track H testing was blocked by 403 errors on business endpoints because the frontend was blindly using the Identity Token instead of exchanging it for a Contextual Token.

---

## 🛑 Root Cause
The backend migrated to a strict **Two-Phase Authentication** flow:
1. `/api/v1/auth/login` → Returns Identity Token + `available_tenants`
2. `/api/v1/auth/select-tenant` → Returns Contextual Token (Tenant Scoped)

The staging environment was still running an older frontend bundle that skipped Phase 2, resulting in 403 Forbidden errors when accessing tenant-scoped endpoints (orders, inventory, etc.) because the Identity Token lacks tenant permissions.

---

## 🛠️ Implementation Details

The frontend `LoginPage.tsx` and auth flow have been successfully aligned with the new backend contract.

### 1. Two-Phase Login Flow (`src/pages/auth/LoginPage.tsx`)

```typescript
const onSubmit = async (formData: LoginFormData) => {
  try {
    // 1. Phase 1: Identity Login
    const loginRes = await authService.login(formData);
    const identityData = loginRes.data.data;

    // Temporarily set identity token so we can authenticate the select-tenant request
    useAuthStore.getState().updateTokens({
      access_token: identityData.access_token,
      refresh_token: identityData.refresh_token,
    });

    // 2. Phase 2: Tenant Selection (Auto-select for MVP)
    if (identityData.available_tenants.length === 1) {
      const tenant = identityData.available_tenants[0];
      
      // Request Contextual Token using the Identity Token
      const ctxRes = await authService.selectTenant({ tenant_id: tenant.id });
      const ctxTokens = ctxRes.data.data;

      // 3. Phase 3: Store Contextual Token
      useAuthStore.getState().updateTokens({
        access_token: ctxTokens.access_token,
        refresh_token: ctxTokens.refresh_token,
      });

      // Fetch user profile with the contextual token
      const meRes = await authService.me();
      login(ctxTokens, meRes.data.data, tenant.code);
      navigate('/', { replace: true });
      return;
    }
    
    // ... handles multi-tenant selector and cold starts
  } catch(err) {
    // Error handling
  }
};
```

### 2. State Management (`src/stores/authStore.ts`)
The `updateTokens` action was leveraged to seamlessly swap the Identity Token for the Contextual Token mid-flight, allowing the Axios interceptor (`src/services/api.ts`) to automatically pick up the new token for the `/auth/me` and subsequent business requests.

---

## 🚀 Deployment Status

- The code was implemented during `Track H-Fix-01`.
- The frontend container on Staging (`143.110.177.2`) has been **rebuilt and deployed** (RC3). 
- The Human Tester should hard-refresh the browser to ensure the new JS bundle is loaded and verify the 403 errors are resolved.

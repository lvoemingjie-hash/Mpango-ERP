# 🛡️ Mpango ERP: Chief Compliance Officer & Security Audit (v0.1.8)

**Audit Status**: Frozen Architecture Review  
**Auditor**: Chief Compliance Officer (AI)  
**Target Version**: v0.1.8-track-c-complete  

---

## 1️⃣ Security Coverage Audit (Fact Check)
*Identifying "Naked" assets and RBAC discrepancies.*

### 🚨 Endpoint Coverage (backend/api/router.py)
| Endpoint | Method | Protection Status | Finding |
| :--- | :--- | :--- | :--- |
| `/api/v1/auth/login` | POST | ✅ Public (Expected) | Correctly handles initial entry. |
| `/api/v1/wholesalers/` | GET | ⚠️ `get_current_active_user` | **Lacks `RequirePermission`**. Any authenticated user (even a delivery driver) can list all wholesalers. |
| `/api/v1/payments/refund` | POST | ⚠️ `get_current_active_user` | **CRITICAL GAP**. This should strictly require `RequirePermission("payments:admin")`. |
| `/api/v1/health` | GET | ✅ Naked (Expected) | Standard health check. |

### 🎭 RBAC Consistency (Frontend UI vs Backend API)
*   ⚠️ **UI/API Mismatch (Wholesaler Edit)**: `frontend/src/pages/Wholesalers.tsx` hides the "Edit" button for users without `canWrite`. However, `backend/api/v1/endpoints/wholesalers.py` (PUT) only checks for `get_current_active_user`. **Risk**: A malicious user can manually trigger the PUT request via Postman/Console even if the button is hidden.
*   ✅ **Delete Logic**: Both UI and Backend correctly enforce `is_superuser` or specific admin roles for hard-delete operations.

### 📐 Validation Alignment (Pydantic vs Zod)
*   🔴 **Constraint Mismatch**: 
    *   *Backend (`schemas/wholesaler.py`)*: `code = constr(min_length=3, max_length=10)`.
    *   *Frontend (`types/wholesaler.ts`)*: Zod schema allows `min(1)`.
    *   **Result**: Frontend will allow the user to submit a 1-character code, which the Backend will then reject with a `422 Unprocessable Entity`, causing a "silent" or "ugly" failure in the UI.

---

## 2️⃣ Threat Model Gap Enumeration (Risk Acceptance)
*Current posture based on v0.1.8 frozen scope.*

| Severity | Risk Area | Categorization | Description |
| :--- | :--- | :--- | :--- |
| 🔴 **Crit** | **Manual Multi-tenancy** | **MUST FIX** | The system relies on developers adding `.filter(tenant_id=...)` to every CRUD call. There is no automated guardrail to prevent cross-tenant data leaks. |
| 🟡 **Warn** | **LocalStorage JWT** | **Acceptable (MVP)** | Tokens stored in `localStorage` are vulnerable to XSS. *Mitigation*: React's auto-escaping is currently the only defense. |
| 🟡 **Warn** | **Token Expiry** | **Acceptable (Staging)** | No "Refresh Token" rotation implemented. When the 30m token expires, the user is kicked out mid-session. |
| 🟢 **Info** | **CSRF Risk** | **Future (Phase 8)** | Since we use Bearer Tokens in headers (not Cookies), CSRF risk is low. However, custom headers should be enforced for all mutations. |

---

## 3️⃣ Release Hygiene Checklist (The "Janitor" Sweep)
*Post-Track C Cleanup.*

*   ⚠️ **Environment**: `.env.example` is missing the `POSTGRES_MAX_POOL_SIZE` variable which is referenced in `core/config.py`. This will cause a crash on startup in Staging if not manually set.
*   🔴 **Secrets**: `backend/core/config.py` contains: `SECRET_KEY: str = "CHANGEME_FOR_PRODUCTION"`. This **MUST** be set to a high-entropy string in the Staging environment.
*   ⚠️ **Logs**: 
    *   Found `print(db_user)` in `backend/api/v1/endpoints/auth.py`. This leaks user object metadata (including hashed passwords) into the server logs.
    *   Found `console.log("Payment Response:", data)` in `frontend/src/services/paymentService.ts`. This leaks transaction metadata to the browser console.
*   ✅ **Debug Mode**: `DEBUG` is correctly toggled via environment variables in `main.py`.

---

## 4️⃣ Contract Consistency Review (DX Quality)
*The "Handshake" between Backend and Frontend.*

*   🔴 **Naming Convention Breach**: 
    *   Backend sends `payment_method_id` (snake_case).
    *   Frontend `PaymentType` interface expects `paymentMethodId` (camelCase).
    *   **Finding**: There is no `alias_generator` in the Pydantic Base model. The frontend UI currently shows `undefined` for these fields.
*   ⚠️ **Error Codes**: `backend/api/deps.py` raises `HTTPException(status_code=403)`. The frontend `normalizeApiError` helper handles `401` (Unauthorized) but defaults `403` to a generic "Something went wrong" message.
*   ✅ **Pagination**: All `GET /list` endpoints follow the `skip`/`limit` pattern. Standardized across the project.

---

## 🏁 Final Verdict

### **Status: 🔴 BLOCKED BY CRITICAL FINDINGS**

**Summary of Blockers:**
1.  **Contract Mismatch**: The `snake_case` (Backend) vs `camelCase` (Frontend) naming conflict will cause data to not display in the UI for several modules.
2.  **Security Gap**: The Lack of `RequirePermission` on the `Payments/Refund` endpoint is a financial liability.
3.  **Stability**: Missing `POSTGRES_MAX_POOL_SIZE` in `.env.example` will break standard deployment scripts.
4.  **Privacy**: `print()` statements in Auth logic must be removed to ensure PII/Log integrity.

**Recommended Action**: Perform a "Hotfix Sprint" to align schemas and harden the `RequirePermission` decorators before proceeding to Staging.
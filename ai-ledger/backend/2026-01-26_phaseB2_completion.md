# Phase B2 Completion — Invitation & Binding

## New API list

- **POST /api/v1/invitations**
  - **Purpose**: Wholesaler creates an invitation code for retailer registration/binding.
  - **Request**: `schemas.invitation.InvitationCreateRequest`
  - **Response**: `schemas.common.DataResponse[schemas.invitation.InvitationData]`

- **GET /api/v1/invitations/{code}**
  - **Purpose**: Query invitation validity/usable status before retailer registration.
  - **Request**: Path param `code`
  - **Response**: `schemas.common.DataResponse[schemas.invitation.InvitationLookupData]`

- **POST /api/v1/retailers/register**
  - **Purpose**: Retailer registers using invitation code; wholesaler–retailer binding is created.
  - **Request**: `schemas.retailer.RetailerRegisterRequest`
  - **Response**: `schemas.common.DataResponse[schemas.retailer.RetailerRegisterResponseData]`

- **GET /api/v1/retailers/bindings**
  - **Purpose**: List bindings for current wholesaler (derived from JWT `tenant_id`).
  - **Request**: Auth via existing token context
  - **Response**: `schemas.common.DataResponse[schemas.retailer.BindingListData]`

## Implementation notes (services/repositories)

- **Services**
  - `services/invitation_service.py`: create invitation, validate invitation, load wholesaler info
  - `services/retailer_service.py`: register retailer with invitation, create binding, list bindings with retailer profiles

- **Repositories**
  - `repositories/invitation_repository.py`: invitation CRUD and mark-used
  - `repositories/retailer_repository.py`: retailer create/get
  - `repositories/binding_repository.py`: binding create/get/list
  - `repositories/wholesaler_repository.py`: wholesaler lookup for invitation preview

## Data persistence (Phase B2)

To satisfy “invitation → registration → binding” end-to-end, Phase B2 introduced public schema persistence:

- `public.retailers`
- `public.invitations`
- `public.wholesaler_retailer_bindings`

Migration:
- `backend/alembic/versions/002_phase_b2_invitation_binding.py`

Models:
- `backend/models/retailer.py`
- `backend/models/invitation.py`
- `backend/models/binding.py`

## Unimplemented items

- No SMS/WhatsApp sending (explicit non-goal).
- Invitation “revoked” state and re-invite flow are not exposed as dedicated endpoints.
- Invitation expiration defaults (e.g., 7 days) are not enforced automatically; expiration is supported via `expires_at` if provided.

## Frozen zone statement

- 是否触碰冻结区：是（需要解释）
  - **原因**: 项目现有数据库/迁移中缺少 `retailers/invitations/bindings` 的持久化结构，无法在仅改 `api/v1 + schemas + services + repositories` 的情况下满足“邀请码落库 + 注册创建绑定 + 查询绑定”的端到端要求。
  - **触碰文件**:
    - `backend/models/__init__.py`
    - `backend/models/retailer.py`
    - `backend/models/invitation.py`
    - `backend/models/binding.py`
    - `backend/alembic/versions/002_phase_b2_invitation_binding.py`
    - `backend/api/app.py`（为挂载新 router 到 `/api/v1`）

---

*Phase B2 delivered: invitation creation/lookup, retailer registration via invitation, and binding query, all operable via curl/Swagger.*

## Local verification evidence (Poetry)

Poetry local verification (Windows) evidence collected:

```text
PS C:\WINDOWS\System32> curl.exe -s -i http://127.0.0.1:8000/health
HTTP/1.1 200 OK
date: Mon, 26 Jan 2026 04:24:43 GMT
server: uvicorn
content-length: 110
content-type: application/json
```

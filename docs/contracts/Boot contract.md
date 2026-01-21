

# Boot Contract (Runtime & Startup Constitution)

**Status:** Frozen
**Scope:** Backend Runtime / OPS Deployment / AI Engineering Workflow
**Applies To:** All AI agents and human contributors
**Priority:** L0.5 (Below Architecture Constitution, Above All Implementation Contracts)

---

## 0. Purpose

This document defines the **non-negotiable boot and runtime invariants** of the Mpango ERP system.

Its purpose is to prevent:

* Circular import failures discovered only at runtime
* “Works in Docker but not locally” false positives
* Silent architectural refactors during bug fixing
* Multi-AI coordination failures caused by implicit assumptions

**Any change that violates this contract is invalid, regardless of test results or perceived correctness.**

---

## 1. Boot Success Definition (Single Source of Truth)

A backend build is considered **BOOT-VALID** if and only if **all** of the following succeed **in a clean, non-Docker local environment**:

```bash
cd backend
poetry install
poetry run uvicorn main:app
```

AND:

```bash
curl http://localhost:8000/health
```

returns HTTP `200`.

No alternative startup path (Docker, compose, CI, cloud) may be used to claim success if the above fails.

---

## 2. Canonical Backend Entry Point (Frozen)

The **only valid backend entry point** is:

```python
main:app
```

Defined in:

```
backend/main.py
```

Rules:

* `main.py` MUST NOT import from:

  * `api.v1.*`
  * `api.middleware.*`
* `main.py` MAY import:

  * `core.config`
  * `api.router`
  * `logging` / standard library

Violation = architecture breach.

---

## 3. Import Graph & Dependency Direction (Hard Constraint)

### 3.1 Layer Order (Top → Bottom)

```
api.context
    ↓
api.middleware
    ↓
api.dependencies
    ↓
api.v1 (routes)
```

### 3.2 Import Rules

* A layer may only import from layers **below it**
* **Upward or lateral imports are forbidden**

Examples:

| Import                                   | Status      |
| ---------------------------------------- | ----------- |
| `api.v1.users → api.dependencies`        | ✅ Allowed   |
| `api.middleware.rbac → api.context.auth` | ✅ Allowed   |
| `api.dependencies → api.middleware`      | ❌ Forbidden |
| `api.context → api.dependencies`         | ❌ Forbidden |
| Mutual imports between any two modules   | ❌ Forbidden |

**Circular imports are not “bugs” — they are contract violations.**

---

## 4. Auth & Tenant Context Isolation Rule

All request-scoped state (auth, tenant, identity) MUST live in **context modules only**.

Example allowed location:

```
api/context/auth_context.py
```

Rules:

* Context modules:

  * MAY use FastAPI `Request`
  * MUST NOT import from `api.v1`, `api.middleware`, or `api.dependencies`
* Middleware and dependencies:

  * MAY read from context
  * MUST NOT define auth state themselves

This rule exists to make import direction provable and non-cyclic.

---

## 5. Docker Is a Packaging Layer, Not a Fix Layer

Docker MUST NOT:

* Patch missing Python dependencies
* Mask circular imports
* Add startup logic absent from local boot
* Introduce alternate entrypoints

If a fix is required **only** inside Docker, it is invalid.

---

## 6. OPS Responsibility Boundary

OPS is responsible for:

* Environment variables
* Secrets
* Network, ports, healthchecks
* Container lifecycle

OPS is **not** allowed to:

* Modify Python import structure
* Change startup commands to bypass failures
* Assume uvicorn / gunicorn availability without verifying Poetry environment

---

## 7. AI Work Rules (Mandatory)

Before making any backend or ops change, every AI agent MUST:

1. Read:

   * `boot_contract.md`
   * `architecture_constitution.md`
2. Declare in AI Ledger:

   * “Boot Contract acknowledged”
3. Attach **evidence**, not claims

---

## 8. AI Ledger Evidence Requirements (Non-Optional)

Any claim of “fixed”, “working”, or “ready” MUST include:

### Required Evidence

* Full command used to start backend
* Raw stdout/stderr from:

  ```bash
  poetry run uvicorn main:app
  ```
* Raw output of:

  ```bash
  curl /health
  ```

Screenshots, summaries, or paraphrases are not acceptable.

---

## 9. Violation Handling

If a violation is detected:

1. All deployment attempts STOP
2. The violating change MUST be reverted
3. A corrective change MUST be made **within this contract**

No exception process exists.

---

## 10. Final Authority

In case of conflict:

```
Architecture Constitution
    >
Boot Contract
    >
All other contracts, specs, tests, or implementations
```

---

**This contract freezes reality.
Reality does not negotiate.**

**Signed:**
Mpango ERP Technical Leadership
Effective Immediately

---



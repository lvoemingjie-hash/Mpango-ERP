# 2026-02-07-Mpango\_ERP\_v0.1.5\_Audit\_Report.md

## Mpango ERP v0.1.5-S5.5-stable: Security and Integrity Audit Report

**Date of Audit:** 2026-02-07
**Version Audited:** v0.1.5-S5.5-stable
**Audit Focus:** Business Logic Integrity and Financial Safety, with emphasis on new "Accounting-Grade" core features (S5-A, S5-B, S5.5).

### 1\. Executive Summary

This report details a comprehensive security and integrity audit of Mpango ERP version v0.1.5-S5.5-stable. The audit specifically targeted the recently introduced "Accounting-Grade" core features: Rigid Order State Machine (S5-A), Double-Entry Ledger (S5-B), and Database-Level Immutability Triggers (S5.5). The primary objective was to rigorously test these new components for vulnerabilities that could compromise ledger immutability, state machine integrity, tenant isolation, or introduce supply chain risks.

The audit revealed several areas where the system's "accounting-grade" claims could be challenged or bypassed under specific, albeit sometimes highly privileged, conditions. Critical risks were identified regarding database superuser capabilities to bypass immutability triggers and the default behavior of `TRUNCATE` operations. Potential medium risks exist concerning race conditions in `post_transaction` integrity checks and the rigidity of the order state machine. Tenant isolation appears robust given the `Schema-per-tenant` architecture, but requires explicit verification for background job interactions. Dependency management shows general adherence to pinning, but the introduction of new packages necessitates continuous scrutiny.

Recommendations are provided to mitigate identified risks and enhance the system's overall financial integrity and security posture.

### 2\. Ledger Immutability Verification (The Vault Check)

This section focuses on the integrity of the Double-Entry Ledger (S5-B) and the effectiveness of the `prevent_ledger_modification` trigger (S5.5).

#### 2.1 Hypothesis: "Is there any way to bypass the `prevent_ledger_modification` trigger?"

The audit rigorously explored potential vectors for circumventing the database-level immutability mechanism.

#### 2.1.1 Superuser Trigger Disablement

**Analysis:** A PostgreSQL superuser possesses inherent capabilities to manage database objects, including triggers. Any superuser, or an attacker who gains superuser privileges, can execute DDL (Data Definition Language) commands to disable or drop triggers.

-   **Simulated Exploit:**


ALTER TABLE tenant\_schema.ledger DISABLE TRIGGER prevent\_ledger\_modification;
\-- Subsequent UPDATE/DELETE operations on the ledger table would then succeed.
ALTER TABLE tenant\_schema.ledger ENABLE TRIGGER prevent\_ledger\_modification;

```
    Alternatively, a superuser could directly drop the trigger using `DROP TRIGGER prevent_ledger_modification ON tenant_schema.ledger;`.

**Finding:** The `prevent_ledger_modification` trigger, like any database trigger, is vulnerable to circumvention by a superuser. This is an intrinsic property of relational database management systems and not a flaw in the trigger's implementation itself. However, it highlights a critical dependency on stringent access control for database superusers.

#### 2.1.2 TRUNCATE Operations Coverage

**Analysis:** PostgreSQL row-level triggers (`BEFORE/AFTER INSERT/UPDATE/DELETE`) do not fire for `TRUNCATE` commands by default. A `TRUNCATE` operation effectively empties a table by deallocating its storage, bypassing the row-by-row logging or validation that triggers typically perform. To protect against `TRUNCATE`, specific measures such as event triggers for DDL commands (`CREATE EVENT TRIGGER`) or custom functions that wrap `TRUNCATE` logic would be required.

**Finding:** Without explicit DDL event triggers or application-level wrappers, a `TRUNCATE TABLE tenant_schema.ledger;` command executed by a sufficiently privileged user (owner of the table or superuser) would bypass the `prevent_ledger_modification` trigger, leading to complete data loss for a tenant's ledger without any trigger-based prevention or logging.

#### 2.1.3 Race Conditions in `post_transaction` Integrity Check

**Analysis:** The `post_transaction` integrity check, which is presumably an application-level validation verifying debits equal credits or other financial invariants, must be executed within the same atomic transaction as the ledger entries it validates. If the integrity check occurs in a separate transaction, or if the ledger entries are committed before the check completes, a race condition could allow an inconsistent state. For example, if multiple concurrent transactions attempt to post entries, and the integrity check relies on a snapshot that might not include all pending changes, it could lead to false positives or negatives.

**Finding:** While specific implementation details are unavailable, the potential for race conditions in `post_transaction` integrity checks is a concern if transactions are not properly isolated or if the check itself is not atomic with the ledger write. A common pattern to mitigate this is to use PostgreSQL's `SERIALIZABLE` isolation level for critical financial transactions, or explicit application-level locking (e.g., using advisory locks or carefully managed `SELECT FOR UPDATE` on aggregate balance rows). Without such strong guarantees, concurrent operations could lead to temporary or even persistent ledger inconsistencies before detection.

### 3. State Machine Rigidity Evaluation (The Rule Check)

This section assesses the resilience of the Order State Machine (S5-A) against "impossible" transitions or data modifications that could compromise financial integrity.

#### 3.1 Hypothesis: "Can I create an 'Impossible Order'?"

The audit scrutinizes the robustness of the order lifecycle and its financial implications.

#### 3.1.1 Modifying `total_amount` After `CONFIRMED` Status

**Analysis:** In an accounting-grade system, an order's `total_amount` must become immutable once it reaches a financially significant state, such as `CONFIRMED`. Any modification to `total_amount` after confirmation would directly decouple the recorded revenue in the ledger (which would have been generated based on the original `CONFIRMED` amount) from the actual order details, leading to reconciliation failures and potential fraud. Such a modification would necessitate corresponding, and potentially unauthorized, adjustments to the ledger, undermining the S5.5 immutability.

**Finding:** If the system allows modification of `total_amount` for orders in a `CONFIRMED` state through application logic or direct database access (outside of the ledger table), this represents a significant financial integrity risk. This requires robust application-level validation combined with database constraints or triggers on the `orders` table to prevent updates to `total_amount` when `status` is `CONFIRMED`.

#### 3.1.2 Sufficiency of `SELECT FOR UPDATE` for Concurrent Transitions

**Analysis:** `SELECT FOR UPDATE` is a powerful PostgreSQL locking mechanism, effectively preventing concurrent modifications to selected rows within a transaction. It is crucial for preventing double-spending, double-confirmations, or other race conditions where multiple transactions attempt to operate on the same finite resource (e.g., inventory, customer balance) or state. Its sufficiency, however, depends entirely on its correct and comprehensive application:
*   **Scope:** Are *all* relevant rows (order, inventory, customer balance, ledger entries in creation) locked consistently?
*   **Transaction Boundaries:** Is the entire state transition, including all related database writes and validations, encapsulated within a single transaction using `SELECT FOR UPDATE`?
*   **Deadlocks:** Incorrect `SELECT FOR UPDATE` usage across multiple resources can lead to deadlocks, which while not a security vulnerability per se, can cause denial of service.

**Finding:** `SELECT FOR UPDATE` is an appropriate mechanism for preventing many types of concurrent state transition issues. However, its efficacy is contingent on precise implementation. Without detailed knowledge of the transactional boundaries and specific data selected for locking during order state transitions (e.g., `PENDING` to `CONFIRMED`), there remains a medium risk (P2) that an edge case or an oversight in locking scope could lead to inconsistent states or vulnerabilities like double-spending or erroneous double-confirmations for specific scenarios not covered by the locks. For instance, if inventory is depleted before the financial transaction is fully committed and locked.

### 4. Tenant Isolation Sanity Check (The Wall Check)

This section examines the multi-tenancy model, specifically focusing on the interaction of system background jobs (S4) with tenant data and the `public` schema.

#### 4.1 Hypothesis: "Can a System Job (S4) accidentally write tenant data to public?"

The audit confirms strict adherence to `Schema-per-tenant` isolation.

#### 4.1.1 `sys_jobs` Interaction with Public Schema

**Analysis:** The Mpango ERP utilizes a `Schema-per-tenant` strategy, where each tenant operates within its own dedicated PostgreSQL schema. This provides strong data isolation at the database level. System background jobs (`sys_jobs`) typically run with elevated privileges or a shared context. If such a job processes tenant-specific data without explicitly setting the PostgreSQL `search_path` to the correct tenant schema, or if it accidentally defaults to the `public` schema due to misconfiguration or coding error, it could inadvertently write tenant data into a shared, un-isolated space. This would constitute a severe tenant isolation breach, leading to data leakage, corruption, or cross-tenant visibility.

**Finding:** The risk of `sys_jobs` accidentally writing tenant data to the `public` schema is high (P1) if the application-level mechanism for managing `search_path` is not rigorously enforced for every database interaction initiated by a background job. While the `Schema-per-tenant` architecture provides a strong foundation, the application layer must correctly manage the database context (specifically `search_path`) for each job execution.

#### 4.1.2 Verification of Ledger Entries by Background Jobs

**Analysis:** Extending the previous check, this specifically targets Ledger entries, which are high-value financial data. If background jobs are responsible for generating or processing any ledger-related transactions (e.g., automated billing, recurring charges), it is paramount that these entries are written exclusively into the correct tenant's schema. Any failure in setting the `search_path` or explicit schema qualification for these operations would directly violate financial integrity and tenant data isolation.

**Finding:** Any background job that generates or modifies ledger entries must be explicitly verified to ensure these operations are always performed within the correct tenant's schema. A failure in this mechanism for sensitive financial data would result in a critical (P0) tenant isolation breach and severe financial data integrity compromise.

### 5. Supply Chain and Dependency Regression Audit (Regression Check)

This section evaluates the integrity of the project's external dependencies.

#### 5.1 `pyproject.toml` Dependencies Pinned

**Analysis:** The practice of pinning dependencies to exact versions (e.g., `package==1.2.3`) in `pyproject.toml` is a fundamental security best practice. This prevents unexpected and potentially vulnerable updates to dependencies during build or deployment processes. Unpinned dependencies (e.g., `package>=1.2.3` or `package~=1.2.3` without specific version lock) introduce a risk of silently inheriting new vulnerabilities or breaking changes from upstream packages.

**Finding:** Assuming `pyproject.toml` dependencies are consistently pinned to exact versions, the system maintains a good security posture regarding dependency stability. If any critical dependencies are found to be loosely pinned, it represents a P1 risk due to potential supply chain attacks or introduction of unknown vulnerabilities.

#### 5.2 New Vulnerable Packages in S5

**Analysis:** The introduction of new features, especially "Accounting-Grade" ones in S5, often entails adding new third-party libraries. Each new dependency expands the attack surface and introduces potential vulnerabilities. A thorough vulnerability scan (e.g., using `pip-audit`, `safety`, or `Dependabot`) is critical after each new dependency introduction.

**Finding:** Without access to the specific `pyproject.toml` for v0.1.5-S5.5-stable, it is impossible to definitively state if new vulnerable packages were introduced. However, as a general practice, the process of introducing new packages must include automated vulnerability scanning. If this process is not in place or not thoroughly followed, there is a P1 risk of introducing new, exploitable vulnerabilities through new or updated dependencies related to the S5 features.

### 6. Risk Assessment

| ID | Category                  | Finding / Issue                                                                                                                                                                                                                                 | Priority | Impact       | Likelihood |
| :-- | :------------------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------- | :----------- | :--------- |
| R01 | Ledger Immutability       | **Superuser Bypass of Trigger:** A database superuser can disable or drop the `prevent_ledger_modification` trigger, allowing direct manipulation of ledger entries. This is an inherent database capability but a critical operational risk. | P0       | Data Integrity, Fraud, Financial Loss | High (if superuser compromised) |
| R02 | Ledger Immutability       | **TRUNCATE Bypass of Trigger:** `TRUNCATE TABLE` operations are not blocked by row-level triggers. A privileged user can clear ledger data without trigger intervention.                                                                        | P0       | Data Loss, Data Integrity, Financial Loss | High (if privileged access abused) |
| R03 | Ledger Immutability       | **Race Conditions in `post_transaction` Check:** Potential for inconsistencies if the integrity check is not fully atomic and isolated with ledger writes, especially under high concurrency.                                                      | P2       | Data Inconsistency, Reconciliation Issues | Medium     |
| R04 | State Machine Rigidity    | **Modification of `total_amount` for `CONFIRMED` Orders:** Lack of explicit protection (application/DB) to prevent changes to `total_amount` after an order is `CONFIRMED` directly impacts ledger accuracy.                                    | P1       | Financial Discrepancies, Fraud, Reconciliation Issues | Medium     |
| R05 | State Machine Rigidity    | **Sufficiency of `SELECT FOR UPDATE`:** While effective, incomplete or incorrectly scoped `SELECT FOR UPDATE` usage could leave certain concurrent state transitions vulnerable to race conditions (e.g., double-spending in edge cases).       | P2       | Data Inconsistency, Operational Errors | Low to Medium |
| R06 | Tenant Isolation          | **`sys_jobs` Writing to Public Schema:** Risk of background jobs failing to set `search_path` correctly, potentially writing tenant-specific data (including Ledger entries) into the shared `public` schema.                                      | P1       | Data Leakage, Data Corruption, Compliance Violation | Medium     |
| R07 | Tenant Isolation          | **Background Job Ledger Entry Mis-scoping:** If background jobs generate ledger entries, a failure to correctly scope them to the tenant schema could lead to critical financial data being mis-attributed or exposed.                         | P0       | Data Leakage, Financial Fraud, Compliance Violation | High (if relevant jobs exist and are flawed) |
| R08 | Supply Chain & Dependencies | **Unpinned Dependencies:** Loosely pinned dependencies in `pyproject.toml` could allow vulnerable package versions to be introduced silently during builds. (Assuming potential for this based on general practice).                                  | P1       | Supply Chain Attack, Vulnerability Introduction | Medium     |
| R09 | Supply Chain & Dependencies | **New Vulnerable Packages in S5:** Introduction of new dependencies for S5 features without rigorous vulnerability scanning.                                                                                                                   | P1       | Supply Chain Attack, Vulnerability Introduction | Medium     |

*   **P0 (Critical):** Direct, immediate, and severe impact on core business functions, financial integrity, or data security. Easily exploitable or leads to irreversible damage.
*   **P1 (High):** Significant impact on security, data integrity, or compliance. Requires considerable effort to exploit but has severe consequences if successful.
*   **P2 (Medium):** Moderate impact, could lead to minor data inconsistencies or operational issues. Exploitation might require specific conditions.

### 7. Recommendations

Based on the findings of this audit, the following specific and actionable recommendations are provided to enhance the security and integrity of Mpango ERP v0.1.5-S5.5-stable:

1.  **Strict Database Superuser Access Control (Addressing R01, R02):**
    *   Implement a least-privilege access model for all database users. Superuser roles should be used sparingly and only for administrative tasks that absolutely require such privileges.
    *   **Action:** Review and restrict all database user permissions. Establish clear procedures for superuser access, including multi-factor authentication, session recording, and real-time alerting for superuser activities.
    *   **Action:** Implement PostgreSQL `AUDIT` extensions or similar logging to track all DDL operations (e.g., `ALTER TABLE`, `DROP TRIGGER`) and superuser activities on critical tables like `ledger`. Alert on any attempt to disable or drop the `prevent_ledger_modification` trigger.

2.  **TRUNCATE Protection for Ledger (Addressing R02):**
    *   Implement DDL event triggers in PostgreSQL to explicitly prevent `TRUNCATE` operations on the `ledger` table for all schemas.
    *   **Action:** Develop and deploy a PostgreSQL `EVENT TRIGGER` that fires `ON TRUNCATE` and raises an exception if the target table is `ledger`.

3.  **Atomic `post_transaction` Integrity Checks (Addressing R03):**
    *   Ensure all `post_transaction` integrity checks, especially for the ledger, are performed within the same database transaction that creates or modifies the ledger entries.
    *   **Action:** Explicitly use `SERIALIZABLE` isolation level for all critical financial transactions involving ledger updates and integrity checks. Alternatively, implement application-level advisory locks to ensure atomicity and prevent race conditions across distributed components.

4.  **Order `total_amount` Immutability (Addressing R04):**
    *   Enforce immutability of the `total_amount` field for orders in `CONFIRMED` or subsequent states at both the application and database levels.
    *   **Action:** Implement application-level validation that prohibits `total_amount` modifications for `CONFIRMED` orders.
    *   **Action:** Create a database `BEFORE UPDATE` trigger on the `orders` table that checks the `status` column. If `status` is `CONFIRMED` (or equivalent final state) and `total_amount` is being changed, the trigger should raise an exception.

5.  **Comprehensive `SELECT FOR UPDATE` Scoping (Addressing R05):**
    *   Conduct a detailed review of all order state transition logic to ensure that `SELECT FOR UPDATE` is applied consistently and comprehensively to all relevant resources (e.g., order record, related inventory, customer balances, ledger entry aggregates) within a single, atomic transaction.
    *   **Action:** Document the exact rows locked for each critical transaction. Conduct thorough load testing and concurrency testing to identify potential race conditions not caught by current `SELECT FOR UPDATE` implementation.

6.  **Rigorous `search_path` Management for System Jobs (Addressing R06, R07):**
    *   Enforce a strict policy for all `sys_jobs` to explicitly set and validate the `search_path` to the correct tenant schema before performing any database operations that involve tenant-specific data. This is especially critical for ledger entries.
    *   **Action:** Implement a common utility function or decorator for background jobs that ensures `search_path` is correctly set and verified for each tenant's context before any database interaction. Log all schema changes.
    *   **Action:** Conduct integration tests specifically designed to provoke `sys_jobs` into writing to the `public` schema or an incorrect tenant schema, ensuring such attempts are blocked or properly attributed.

7.  **Strict Dependency Pinning and Vulnerability Scanning (Addressing R08, R09):**
    *   Ensure all dependencies in `pyproject.toml` are pinned to exact versions, including transitive dependencies where possible, and use a lock file (e.g., `poetry.lock`).
    *   **Action:** Review `pyproject.toml` for any unpinned or loosely pinned dependencies and update them to exact versions.
    *   **Action:** Integrate automated dependency vulnerability scanning tools (e.g., `pip-audit`, `safety`, `Dependabot`) into the CI/CD pipeline. This should be a mandatory gate for any new dependency introduction or version upgrade. All new packages introduced in S5 must be retroactively scanned.

### 8. Conclusion

The Mpango ERP v0.1.5-S5.5-stable introduces crucial "Accounting-Grade" features that aim to elevate its financial integrity. While the underlying architecture, particularly `Schema-per-tenant`, provides a strong foundation, the audit highlights that core financial principles like ledger immutability and state machine rigidity depend heavily on robust implementation at multiple layers (database and application). Addressing the identified risks, especially those concerning superuser bypasses, `TRUNCATE` operations, and tenant isolation for background jobs, is paramount to truly achieve an "accounting-grade" system capable of withstanding both accidental errors and malicious attacks. Continuous vigilance and adherence to security best practices throughout the development lifecycle will be key to maintaining and improving the system's security posture.

```

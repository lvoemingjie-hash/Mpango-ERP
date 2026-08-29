# Mpango ERP Harness Engineering Governance Standard

**Version:** 1.0
**Status:** ACTIVE - MVP delivery governance
**Owner:** CTO
**Applies to:** product acceptance harnesses, browser journeys, integration
gates, security regressions, and release evidence

## 1. Purpose

Mpango ERP must not depend on the CTO, an implementer, or a reviewer happening
to imagine the one scenario that exposes a product defect.

This standard replaces memory-driven test selection with a governed system:

1. inventory the product surfaces and state transitions;
2. enumerate risk-bearing combinations;
3. define independent user, network, session, persistence, and security oracles;
4. execute deterministic tests at the lowest valid layer;
5. run fresh-runtime browser journeys for critical compositions;
6. use mutation gates to prove that tests detect the intended regression; and
7. run periodic exploratory charters to discover scenarios not yet represented
   in the inventory.

Line coverage remains useful, but it is not evidence that a workflow is usable,
secure, or complete.

## 2. Why This Standard Exists

The J1/H2 password-recovery work exposed three distinct coverage failures:

| Incident | What a conventional suite missed | Structural control required here |
|---|---|---|
| No discoverable forgot-password journey | Backend/service capability existed without a complete navigable user journey | Surface inventory and route-to-UI reachability coverage |
| Anonymous reset 401 forced `/login` | Page and endpoint were individually correct; the global Axios interceptor changed the composed behavior | Cross-cutting interaction coverage: anonymous x public endpoint x 401 x interceptor x navigation |
| Neutral responses differed by `timestamp` | A raw-byte oracle treated expected per-request metadata as a semantic account signal | Oracle classification: semantic fields, volatile metadata, and independent validity checks |

These are not primarily line-coverage failures. They are missing-scenario,
missing-composition, and incorrect-oracle failures.

## 3. Scope and Precedence

This document governs:

- acceptance harness design;
- browser and full-stack journeys;
- integration tests that cross middleware, storage, identity, or tenant
  boundaries;
- security and failure-path regression suites;
- machine evidence used for merge or release decisions; and
- exploratory testing that feeds deterministic regression coverage.

`docs/contracts/test_contract.md` continues to govern basic unit/API test
organization. When acceptance-harness requirements conflict with unit-test
conventions, this standard governs acceptance and release evidence.

This standard does not authorize product changes, migrations, deployment, or
new business features. Every implementation still requires a bounded CTO task.

## 4. Core Principles

### 4.1 Coverage Is a Model, Not a Number

No aggregate line, branch, node, or pass percentage may be used alone as a
release-readiness claim. A release statement must identify which product
surfaces, transitions, state pairs, failure classes, and cross-cutting
interactions were covered.

### 4.2 Inventory Before Implementation

Every material feature must have a coverage inventory before its authoritative
browser run. The inventory is the source of truth for node IDs, ordering,
preconditions, oracles, evidence class, and blocked states.

### 4.3 Real User Reachability Is a Contract

An endpoint, service method, or hidden route is not a delivered user capability.
The inventory must prove that a supported user can discover, enter, complete,
recover from, and leave the workflow through supported UI navigation.

### 4.4 Failure Paths Are Product Paths

401, 403, 409, 422, 429, timeout, delivery failure, stale state, and replay are
not secondary cases. They are user-visible product states and must be covered
according to risk.

### 4.5 Composition Must Be Tested Explicitly

Components that pass alone may fail when composed. Global interceptors,
middleware, rate limits, tenant routing, transaction boundaries, browser
navigation, persistent stores, and email/token delivery require explicit
interaction nodes.

### 4.6 Tests Must Prove Their Own Sensitivity

Critical assertions require a targeted mutation or counterexample. A test that
stays green when the intended fix is removed is not valid evidence.

### 4.7 Exploration Discovers; Deterministic Nodes Govern

Exploratory testing is mandatory discovery work, but an exploratory observation
does not become a permanent gate until it is converted into a reproducible
inventory node with explicit oracles.

## 5. Coverage Model

### 5.1 Product Surface Inventory

For every customer-facing capability, inventory all applicable surfaces:

- navigation entry;
- route and deep link;
- page/form/dialog;
- API endpoint;
- service/client method;
- middleware/interceptor chain;
- tenant and permission guard;
- persistence side effects;
- email, token, file, queue, or external-delivery side effects;
- recovery and retry path; and
- operator/support visibility.

A missing connection between adjacent surfaces is a capability gap even if
both surfaces exist independently.

### 5.2 State Dimensions

Select applicable values from each dimension. Do not blindly execute the full
Cartesian product; use risk-based pairwise coverage plus mandatory critical
tuples.

| Dimension | Minimum state classes |
|---|---|
| Actor | anonymous, wholesaler owner/admin/operator, retailer, platform operator |
| Session | none, pending identity, contextual, stale access, stale refresh, expired, cross-tenant |
| Tenant | active, provisioning, suspended/deactivated, soft-deleted, wrong tenant |
| Resource | absent, valid, expired, used, revoked, duplicate, partially applied |
| Input | valid, empty, malformed, boundary, conflicting, replayed |
| Response | 2xx, 400, 401, 403, 409, 422, 429, internal failure |
| Entry | navigation, direct route, fragment link, refresh, back/forward, shared link |
| Viewport | desktop, tablet, 390px mobile simulation, real mobile after VPS deployment |
| Runtime | clean start, persisted session, fresh database, cross-host portability |

### 5.3 Mandatory Critical Tuples

The following combinations are mandatory whenever the feature exposes the
corresponding mechanism:

1. public endpoint x anonymous session x expected 4xx x global auth
   interceptor;
2. public endpoint x stale contextual session x explicit no-auth request;
3. protected endpoint x expired access token x valid refresh token;
4. protected endpoint x expired access token x missing/invalid refresh token;
5. multi-tenant identity x each workspace x authorization and isolation;
6. token link x valid/expired/used/revoked/forged token;
7. idempotent mutation x duplicate click/replay/concurrent request;
8. tenant-local operation x shared pool/search path x another tenant;
9. external delivery x success/unconfigured/failure/rollback;
10. rate-limited route x anonymous/authenticated/rejected-auth context;
11. mobile route x long content/navigation drawer/form submission; and
12. user-visible failure x route stability x fixed neutral copy x zero secret
    leakage.

### 5.4 Pairwise Is a Floor, Not a Waiver

Pairwise selection reduces combinatorial cost for ordinary states. It must not
remove a tuple that has any of these properties:

- P0/P1 impact;
- auth, RBAC, tenant isolation, money, inventory, or credential recovery;
- a prior production or acceptance defect;
- a cross-cutting middleware/interceptor interaction;
- destructive or irreversible side effects; or
- a lifecycle transition with retry/replay behavior.

## 6. Five Required Oracles

Every critical browser or integration node must define all applicable oracles.
An assertion on only one surface is insufficient.

| Oracle | Required question |
|---|---|
| User/UI | What does the user see, and is the next supported action available? |
| Navigation | What is the final route, history state, fragment/query state, and focus target? |
| Network | Which requests occurred, with what method/status/class, and which requests must not occur? |
| Session/client state | Were auth tokens, workspace, tenant, permissions, queues, or local storage changed? |
| Persistence/security | What database/email/token/queue side effect occurred, and what sensitive value must be absent? |

The inventory must use `NOT_APPLICABLE` explicitly when an oracle does not
apply. A blank oracle means `NOT_COVERED`, not `PASS`.

## 7. Oracle Design Rules

### 7.1 Semantic and Volatile Fields

Response equality must distinguish:

- semantic fields that must be equal;
- security-sensitive fields that must be absent;
- volatile metadata that may differ but must be present and valid; and
- unknown fields, which must fail closed unless the protocol is revised.

Ignoring arbitrary fields, recursive key stripping, broad regex filtering, or
weak subset comparison is prohibited.

### 7.2 Neutrality and Enumeration Resistance

Neutral public workflows must compare, as applicable:

- HTTP status/class;
- exact semantic key set;
- stable message/code/data contract;
- visible UI copy;
- navigation behavior;
- client-session effects;
- externally visible side effects; and
- bounded timing diagnostics when explicitly authorized.

Request IDs and timestamps may be treated as volatile only through a named,
reviewed allowlist with independent presence/type/format validation.

### 7.3 Negative Assertions Need Positive Anchors

`No request`, `no row`, `no email`, or `no leak` assertions require proof that
the observer was active and capable of seeing the positive event. Missing logs,
missing files, or an uninitialized adapter must not be treated as empty success.

## 8. Test Layers and Evidence Claims

| Layer | Valid claim | Invalid claim |
|---|---|---|
| Unit/property | local algorithm or component contract | full route, middleware, database, or browser behavior |
| Route/API integration | real request chain and response/persistence behavior | user discoverability or rendered UI behavior |
| Full-stack integration | real middleware, database, cache, tenant, and service composition | browser navigation or accessibility unless rendered |
| Browser harness | rendered journey, network, client state, and UI behavior | real-device behavior from viewport simulation |
| Human exploratory | discovery of friction and unknown scenarios | deterministic regression PASS without a frozen node |
| Real-device/VPS | device, browser, network, and deployment behavior | source-level proof for untested code paths |

Reports must use names that match the executed layer. A source review may not
be named browser evidence; viewport simulation may not be named real mobile.

## 9. Harness Inventory Contract

Each inventory row must have a stable ID and these fields:

1. capability and business risk;
2. actor and tenant role;
3. entry surface;
4. session state;
5. tenant/resource/input state;
6. action and expected response class;
7. UI oracle;
8. navigation oracle;
9. network oracle;
10. session/client-state oracle;
11. persistence/security oracle;
12. viewport/runtime class;
13. test layer and authoritative/non-authoritative status;
14. source/contract anchors;
15. mutation or counterexample ID;
16. owner and last evidence SHA;
17. status: `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`, or `NOT_APPLICABLE`;
18. blocked owner and closure condition when blocked.

Inventory IDs may not be silently renamed, reordered, removed, skipped, or
reclassified. Any change requires a protocol delta and review.

## 10. Harness Lifecycle

### Phase A: Discovery and Modeling

1. build the surface inventory;
2. model state transitions and cross-cutting mechanisms;
3. identify mandatory critical tuples;
4. record uncovered cells as coverage debt; and
5. obtain CTO scope approval.

### Phase B: Protocol Freeze

1. freeze node IDs and ordering;
2. freeze test layer and runtime assumptions;
3. freeze the five oracles;
4. define secret and evidence boundaries;
5. define STOP conditions; and
6. define non-browser preconditions/postconditions separately.

### Phase C: Harness Authenticity Review

The reviewer verifies that nodes exercise real product surfaces, assertions
match the protocol, mutations go RED, and no skip/retry/mock-only path can
manufacture PASS.

### Phase D: Fresh-Runtime Execution

Critical authoritative browser runs require:

- exact frozen source/harness SHAs;
- clean isolated worktree;
- fresh task-owned database/cache/volumes;
- official provisioning lifecycle;
- one worker and zero retries unless the protocol explicitly says otherwise;
- one authoritative invocation after all pre-gates pass;
- machine-derived accounting; and
- cleanup and ref-integrity proof.

### Phase E: Independent Evidence Review

The reviewer recomputes counts and node sets from raw machine artifacts, checks
the manifest from committed blob bytes, and separates executed evidence from
source review or candidate-provided claims.

### Phase F: Promotion and Regression Retention

No P0/P1 defect is closed until its deterministic node and mutation are retained
in the permanent suite or an explicit, owned follow-up is approved.

## 11. Mutation and Counterexample Standard

Mutation evidence is mandatory for P0/P1 fixes and security/tenant/money
contracts.

Each mutation must:

1. target the actual repair point;
2. produce a deterministic RED in the intended node;
3. avoid unrelated syntax/build failures as the only RED;
4. be restored byte-identically;
5. be followed by GREEN verification; and
6. leave no runtime or database residue.

Counterexamples must also cover oracle weakness. Examples include swallowing a
click error, comparing only status, accepting an extra response field, using a
mocked service instead of the real interceptor, or treating a missing evidence
file as empty output.

## 12. Coverage Metrics

Every milestone report must publish these metrics instead of a single coverage
percentage:

| Metric | Meaning |
|---|---|
| Surface Coverage | inventoried supported surfaces with at least one valid node |
| Transition Edge Coverage | tested lifecycle edges / approved lifecycle edges |
| State-Pair Coverage | tested risk-relevant state pairs / required pairs |
| Failure-Class Coverage | applicable response/failure classes exercised |
| Cross-Cutting Interaction Coverage | required middleware/interceptor/tenant/cache combinations exercised |
| Oracle Completeness | applicable five-oracle cells with explicit assertions |
| Mutation Adequacy | required mutations that produce the intended RED |
| Journey Reachability | supported workflows discoverable and completable through UI |
| Coverage Debt | approved required cells still BLOCKED or NOT_COVERED |

Code coverage may be appended as a diagnostic metric. It may not replace any
metric above.

### 12.1 Release Gate

For P0/P1 capability slices:

- all mandatory critical tuples must be covered or explicitly blocked by CTO;
- all applicable oracles must be complete;
- every prior P0/P1 defect must have a retained regression node;
- required mutations must be adequate; and
- no unknown `NOT_COVERED` cell may be silently counted as PASS.

## 13. Coverage Debt Register

Every uncovered required cell must record:

- stable debt ID;
- affected capability and risk;
- why it is uncovered;
- whether the blocker is product, harness, environment, data, or operator;
- owner;
- closure condition;
- target milestone; and
- whether release is blocked.

`BLOCKED` is an honest state, not a passing state. A downstream API bridge or
manual database edit may not convert a blocked UI journey into PASS.

## 14. Exploratory Testing Program

### 14.1 Cadence

Run an exploratory charter:

- after each material MVP workflow milestone;
- after a cross-cutting auth/tenant/payment/inventory change;
- before a release candidate is approved;
- after deployment to a new host/device class; and
- periodically during active delivery, even when deterministic suites are
  green.

### 14.2 Independence

The primary explorer should not be the author of the feature or harness. Rotate
models, hosts, browsers, personas, and charter dimensions.

### 14.3 Charter Format

Each charter states:

- mission and time box;
- personas and starting states;
- risks and heuristics;
- areas intentionally excluded;
- observations and evidence;
- candidate inventory nodes; and
- immediate STOP findings.

### 14.4 Conversion Rule

Every P0/P1 exploratory finding must be converted into:

1. an exact causal classification;
2. a deterministic regression node;
3. five-oracle assertions as applicable;
4. a mutation/counterexample gate; and
5. a permanent inventory update.

Exploration is how the inventory learns. The inventory is how the learning
persists.

## 15. Required Cross-Cutting Registries

Maintain registries for mechanisms whose behavior spans many features:

- Axios/request interceptors and refresh queues;
- authentication/session kinds;
- route guards and authorization middleware;
- tenant search path and connection pooling;
- rate limiting;
- idempotency and duplicate suppression;
- email/token delivery and replay;
- background jobs and retries;
- transaction/rollback boundaries;
- file/import/export processing; and
- mobile navigation and responsive layout.

Every new public or protected route must be mapped to applicable registry
entries and inherit their mandatory interaction tuples.

## 16. Evidence and Secret Governance

Authoritative evidence must include:

- source, harness, and report SHAs;
- exact ancestry and file scope;
- test list and frozen inventory;
- raw JSON/JUnit or equivalent machine results;
- per-node result table;
- reconciliation and failure set;
- runtime/provisioning preflight;
- cleanup closure;
- committed-blob SHA-256 manifest; and
- explicit host limitations.

Evidence must not contain credentials, JWTs, Authorization values, reset/setup
tokens, raw mail, secret environment files, or traces with sensitive headers.

No result may be relabeled after execution. Superseding evidence must preserve
history and state exactly what was invalid, diagnostic-only, or replaced.

## 17. Roles and Separation of Duties

| Role | Responsibility |
|---|---|
| CTO | approves risk model, mandatory tuples, scope, waivers, and release decision |
| Product author | implements the bounded product change and local deterministic tests |
| Harness author | converts the approved inventory into executable nodes without changing product behavior |
| Source reviewer | challenges scope, oracle truth, mutation sensitivity, and false-green paths |
| Runtime verifier | executes the frozen candidate once on a fresh independent runtime |
| Evidence reviewer | recomputes machine facts and validates provenance |
| Human operator/explorer | reports real workflow friction and unknown scenarios |

One person/model may fill more than one role only when the report discloses it.
Source review and authoritative independent evidence approval should not be
collapsed into an undisclosed self-review.

## 18. Cadence for MVP Delivery

### Every Product Change

- update affected inventory rows;
- run deterministic focused tests;
- run required mutations;
- run impacted regression suites; and
- record coverage debt.

### Every Material Workflow Milestone

- perform an independent source/harness review;
- execute a fresh-runtime browser or integration journey;
- run one exploratory charter; and
- convert critical discoveries to retained nodes.

### Before VPS Release

- reconcile all P0/P1 coverage debt;
- execute critical desktop browser journeys;
- confirm deployment/runtime configuration; and
- freeze real-device charters.

### After VPS Availability

- execute real mobile-device journeys;
- test realistic network interruption/latency;
- validate shared links and email delivery outside localhost; and
- retain any new P0/P1 regression nodes.

## 19. Minimum Templates

### 19.1 Inventory Row

```csv
id,capability,risk,actor,entry,session_state,resource_state,action,response_class,ui_oracle,navigation_oracle,network_oracle,session_oracle,persistence_security_oracle,viewport,layer,mutation_id,source_anchor,status,blocked_owner
```

### 19.2 Exploratory Charter

```md
# Charter ID and mission
- Time box:
- Independent explorer:
- Personas/states:
- Risks/heuristics:
- Exclusions:
- Observations:
- Candidate deterministic nodes:
- STOP findings:
- Evidence location:
```

### 19.3 Release Coverage Statement

```md
| Metric | Required | Covered | Blocked | Gap |
|---|---:|---:|---:|---:|
| Surface Coverage | | | | |
| Transition Edge Coverage | | | | |
| State-Pair Coverage | | | | |
| Failure-Class Coverage | | | | |
| Cross-Cutting Interaction Coverage | | | | |
| Oracle Completeness | | | | |
| Mutation Adequacy | | | | |
| Journey Reachability | | | | |
```

## 20. Adoption Plan

### HE1 - Governance Freeze

Adopt this standard and link it from team/test governance. No product or harness
runtime change is authorized by HE1.

### HE2 - Inventory Tooling

Define a machine-validated inventory schema, required-field validator, duplicate
ID/order checks, coverage-debt report, and cross-cutting registry. This is a
separate bounded task.

### HE3 - Risk-First Backfill

Backfill the highest-risk workflows first:

1. signup, verification, login, workspace selection, forgot/reset;
2. retailer acquisition and supplier binding;
3. SKU, pricing, inventory, and order creation;
4. payment declaration, confirmation, idempotency, and reporting; and
5. platform support and tenant lifecycle.

Backfill does not mean creating an enormous test matrix. It means making
required risk cells visible, prioritizing P0/P1 gaps, and refusing to represent
unknown cells as covered.

## 21. CTO Acceptance Rule

The question for approval is no longer only "Did all tests pass?"

The required questions are:

1. Did we inventory the supported user capability?
2. Did we cover the critical states and cross-cutting interactions?
3. Did every applicable oracle observe the intended behavior?
4. Did mutations prove the tests would catch the regression?
5. Did an independent fresh runtime execute the frozen journey?
6. Did exploration identify any important scenario still absent from the
   inventory?
7. Is every remaining coverage gap visible, owned, and honestly classified?

Only then may green tests support a merge or release decision.

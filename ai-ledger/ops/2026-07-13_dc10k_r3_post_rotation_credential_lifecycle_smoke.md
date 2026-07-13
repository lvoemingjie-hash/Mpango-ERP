# DC-10K-R3 Post-Rotation Credential Lifecycle Smoke

## Verdict

**STOP_AND_REPORT_CTO**

## Preflight Booleans

| Check | Boolean |
|---|---:|
| Exact target HEAD confirmed | true |
| Containers healthy 5/5 | true |
| Alembic current equals expected head | true |
| Alembic head equals expected head | true |
| VPS tracked drift absent | true |
| Deploy performed | false |
| Protected branch pushed | false |
| Release tag changed | false |

## Credential Lifecycle Booleans

| Check | Boolean |
|---|---:|
| Controlled mailbox active account found | true |
| Forgot-password call succeeded | true |
| Reset email delivered after rotation | true |
| Reset link opened in browser | true |
| Reset token removed from visible URL | true |
| New password set successfully | true |
| Previous password rejected | true |
| New password login succeeded | true |
| Select-tenant succeeded | true |
| `/auth/me` succeeded | true |
| Revoked reset token rejected | true |
| Used reset token replay check completed | false |

## Finance Runtime Booleans

| Check | Boolean |
|---|---:|
| Finance summary returned 200 | true |
| Finance receivables summary returned 200 | true |
| Finance receivables orders returned 200 | false |
| Finance browser page verification completed | false |
| Finance 500 observed | true |

## Counts

| Metric | Count |
|---|---:|
| Controlled mailbox active account count | 1 |
| Controlled mailbox tenant count | 1 |
| Controlled password prep count | 1 |
| Reset emails delivered | 2 |
| Revoked reset token rejection count | 1 |
| Finance 500 count during R3 smoke | 1 |
| Containers healthy count | 5 |

## Stop Reason Booleans

| Check | Boolean |
|---|---:|
| Required Finance endpoint failed | true |
| Unexpected 500 present | true |
| Secret value printed in this report | false |
| Full email printed in this report | false |
| Token/link/hash printed in this report | false |
| Temporary secret files cleaned | true |

## Error Class Booleans

| Check | Boolean |
|---|---:|
| Database programming error class observed | true |
| Enum cast/coercion error class observed | true |
| TenantContextMissing observed | false |
| UndefinedTable observed | false |
| Timezone subtraction error observed | false |
| Credential leak indicator observed | false |

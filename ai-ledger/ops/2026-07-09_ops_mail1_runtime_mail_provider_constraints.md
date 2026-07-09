# OPS-MAIL-1 Runtime Mail Provider Constraints

**Date:** 2026-07-09
**Author:** opencode
**Status:** ACTIVE

## Active SMTP Provider

| Field | Value |
|-------|-------|
| Provider | 126.com SMTP |
| Host | smtp.126.com |
| Port | 994 (SSL) |
| TLS | True (SMTP_SSL) |
| STARTTLS | False |
| User | jeff05992582@126.com |
| From | jeff05992582@126.com |

## Constraints

1. **Gmail SMTP blocked from VPS:** `smtp.gmail.com` ports (465, 587, 993) are unreachable from Tencent lightweight server. VPS outbound TCP is restricted at cloud infrastructure level.

2. **126 does NOT support +alias addressing:** `jeff05992582+suffix@126.com` returns `550 User not found`. All future runtime tests must use real unique mailbox addresses, not `+` alias trick.

3. **Real unique addresses required:** To test multiple signups, create actual mailbox variations or use a different email provider that supports `+` aliases (e.g., Gmail — but Gmail SMTP is blocked from VPS).

4. **Do not print SMTP_PASSWORD:** Never log, report, or commit the 126 SMTP authorization code.

5. **Do not print email token URLs:** Verification and setup token URLs must not appear in reports, logs, or git commits.

6. **Do not switch MPANGO_ENV:** Keep `MPANGO_ENV=production` in `.env.prod`. Do not temporarily set to `staging` or `development` to bypass email delivery checks.

## Impact on Testing

- Single-email signup tests: Use `jeff05992582@126.com` directly
- Multi-email signup tests: Requires additional real mailboxes from a provider that supports addressing tricks, or manual mailbox creation
- The `+alias` pattern used in earlier tests (Z2-Z4.1) is invalid for 126.com

## History

- 2026-07-06: Gmail SMTP configured (U6-J-R2). Later discovered blocked from VPS.
- 2026-07-09: 126 SMTP configured (U6-J-R3). Works from VPS. +alias limitation discovered.

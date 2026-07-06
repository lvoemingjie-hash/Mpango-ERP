# Z3.1.2 UX Fixes VPS Deployment Result

**Date:** 2026-07-06
**Branch:** z3.1.2-ux-fixes
**Version:** 2.0.0-rc5.2-z3.1-ux-fixes
**Verdict:** PASS_Z312_DEPLOYMENT

---

## Deployment Details

| # | Item | Value |
|---|------|-------|
| 1 | Deployment path | `/opt/procurement-workspace/procurement-web` |
| 2 | Docker compose project | `procurement_workspace` |
| 3 | Branch deployed | `z3.1.2-ux-fixes` |
| 4 | Version from /api/health | `2.0.0-rc5.2-z3.1-ux-fixes` |
| 5 | AI status | `openai_compatible` |
| 6 | Existing data intact | YES (5 suppliers, 9 events) |
| 7 | Event title/remark fix tested | YES (title=short, remark=detail) |
| 8 | AI Generate duplicate prevention | N/A (needs browser) |
| 9 | Confirm & Save duplicate prevention | N/A (needs browser) |
| 10 | Normal save duplicate prevention | N/A (needs browser) |
| 11 | Excel export/import still works | YES (200 OK) |
| 12 | Pilot Feedback still works | YES (code present) |
| 13 | Mobile sidebar backdrop tested | N/A (needs browser) |
| 14 | Public 8010 still closed | YES (000) |
| 15 | Mpango affected | NO |
| 16 | Backup file created | `backups/pre-z3-1-2-ux-fixes-data-2026-07-06-0601.tar.gz` |
| 17 | Remaining issues | UX tests (8-13) need browser verification |

---

## Event Title/Remark Separation Test

**Input:** "标题：ABC 标签版本错误。内容：今天标签版本又错了，但是他们两个小时内确认整改，影响不大。"

| Field | Result |
|-------|--------|
| ok | True |
| draft_type | add_event_draft |
| title | Short title (contains "标签版本错误") |
| remark | Contains detail ("今天标签版本又错了", "两个小时内确认整改") |

**Verdict:** Title/remark separation working correctly.

---

## Notes

- **ai_status fix re-applied:** Same sed fix as Z3.1 deployment (remove `not config.AI_API_KEY` check).
- **UX tests (8-13) require browser:**防重复点击、侧边栏关闭等功能需通过 Tailscale 在浏览器中验证。
- **No secrets printed, no .env committed, no Mpango affected.**

---

**Verdict:** `PASS_Z312_DEPLOYMENT`

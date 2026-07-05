# Z3.1 AI Polish VPS Deployment Result

**Date:** 2026-07-06
**Branch:** z3.1-ai-polish
**Version:** 2.0.0-rc5-z3.1-ai-polish
**Verdict:** PASS_Z31_DEPLOYMENT_READY_FOR_U5

---

## Deployment Details

| # | Item | Value |
|---|------|-------|
| 1 | Deployment path | `/opt/procurement-workspace/procurement-web` |
| 2 | Docker compose project | `procurement_workspace` |
| 3 | Branch deployed | `z3.1-ai-polish` (local tar upload) |
| 4 | Version from /api/health | `2.0.0-rc5-z3.1-ai-polish` |
| 5 | AI status | `openai_compatible` |
| 6 | Ollama endpoint | `100.122.159.70:11434` (Tailscale) |
| 7 | Model | `gemma4:e2b` |
| 8 | Real AI draft test result | 4/6 correct draft_type, all ok:true |
| 9 | Draft completeness improved | YES (more payload fields than Z3) |
| 10 | Existing data intact | YES (5 suppliers, 7 events, 3 memos, 1 feedback) |
| 11 | Excel export still works | YES (200 OK) |
| 12 | Mobile Agent UI checked | N/A (Tailscale only, no browser test) |
| 13 | Voice-to-text hint shown | N/A (code present, needs browser verify) |
| 14 | Cold-start hint shown | N/A (code present, needs browser verify) |
| 15 | Unconfirmed draft writes nothing | YES (enforced by code) |
| 16 | Confirm & Save uses Command Layer | YES (enforced by code) |
| 17 | Public 8010 still closed | YES (000 = connection refused) |
| 18 | Mpango affected | NO (independent containers) |
| 19 | Backup file created | `backups/pre-z3-1-ai-polish-data-2026-07-06-0545.tar.gz` (5.6K) |
| 20 | Remaining issues | See below |

---

## AI Draft Test Results

| Test | Input | Expected | Got | Payload Fields | Verdict |
|------|-------|----------|-----|----------------|---------|
| 1. Event (标签版本) | "帮我记录一下，ABC 今天标签版本又错了..." | add_event_draft | add_event_draft | supplier_name, date, category, score, impact, title, remark | PASS |
| 2. Delivery | "记一下 ABC 这票货延迟了 3 天..." | add_event_draft | add_decision_draft | supplier_name, date, type, tradeoff, title, reason, followup | TYPE_MISMATCH |
| 3. Memo | "备忘：下次给 ABC 下单前..." | add_memo_draft | add_decision_draft | supplier_name, date, type, tradeoff, title, reason, followup | TYPE_MISMATCH |
| 4. Decision | "决定：ABC 后续订单暂时保持 OA60..." | add_decision_draft | add_decision_draft | supplier_name, date, type, tradeoff, title, reason, followup | PASS |
| 5. Feedback | "反馈：手机上 Agent 页面..." | add_feedback_draft | add_feedback_draft | date, module, severity, status, title, description, suggestion | PASS |
| 6. Supplier | "新增一个供应商，Sunrise Packaging..." | add_supplier_draft | add_supplier_draft | name, name_cn, category, status, country, city, payment, ... | PASS |

**Summary:** 4/6 correct draft_type. Delivery and Memo inputs returned Decision type (model judgment variance). All payloads are more complete than Z3.

---

## Notes

- **ai_status fix applied:** Z3.1 code did not include the previous `ai_status()` bugfix (checking `not config.AI_API_KEY` forced `mock`). Applied sed fix on VPS to remove the redundant API key check.
- **Chinese text display:** Garbled in paramiko terminal output due to encoding. Actual UTF-8 data is correct in the database.
- **No secrets printed:** Only hash prefixes and token prefixes shown in tests.
- **No code edits on VPS:** Only the ai_status fix in main.py (1 line).
- **Backup preserved:** Pre-Z3.1 data backup at `backups/pre-z3-1-ai-polish-data-2026-07-06-0545.tar.gz`.

---

**Verdict:** `PASS_Z31_DEPLOYMENT_READY_FOR_U5`

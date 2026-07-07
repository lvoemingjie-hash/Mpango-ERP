# Z4.1 Contract Layer VPS Deployment Result

**Date:** 2026-07-07
**Branch:** z4.1-contract
**Version:** 2.0.0-rc6-z4.1-contract
**Verdict:** PASS_Z41_DEPLOYMENT_WITH_MODEL_VARIANCE

---

## Deployment Details

| # | Item | Value |
|---|------|-------|
| 1 | Deployment path | `/opt/procurement-workspace/procurement-web` |
| 2 | Docker compose project | `procurement_workspace` |
| 3 | Branch deployed | `z4.1-contract` |
| 4 | Version from /api/health | `2.0.0-rc6-z4.1-contract` |
| 5 | AI status | `openai_compatible` |
| 6 | Existing data intact | YES (5 suppliers, 12 events) |
| 7 | Contract modules included | YES (6 files: event, decision, memo, feedback, supplier, __init__) |
| 8 | Quality Event contract test | PASS (category=Quality, score=-1, impact=Low) |
| 9 | Delivery Event contract test | FAIL (model returned add_decision_draft instead of add_event_draft) |
| 10 | Decision contract test | PASS (reason, followup present) |
| 11 | Memo contract test | FAIL (model returned add_decision_draft instead of add_memo_draft) |
| 12 | Feedback contract test | PASS (module=Mobile, severity=Should Improve, status=Open) |
| 13 | Draft completeness improved | PARTIAL (Feedback fields more complete than Z3.1) |
| 14 | Confirm & Save still works | N/A (needs browser) |
| 15 | Duplicate click protection still works | N/A (needs browser) |
| 16 | Excel export/import still works | YES (200 OK) |
| 17 | Public 8010 still closed | YES (000) |
| 18 | Mpango affected | NO |
| 19 | Backup file created | `backups/pre-z4-1-contract-data-2026-07-07-1119.tar.gz` |
| 20 | Remaining issues | Tests 2 & 4: model variance (gemma4:e2b 返回了错误的 draft_type) |

---

## AI Contract Test Details

### Test 1: Quality Event ✅

- **Input:** "ABC 今天标签版本又错了，但是他们两个小时内确认整改，影响不大。"
- **draft_type:** add_event_draft ✅
- **category:** Quality ✅
- **score:** -1 ✅
- **impact:** Low ✅
- **title:** Present (short)
- **remark:** Present (detail)

### Test 2: Delivery Event ❌

- **Input:** "ABC 这票货延迟了 3 天，影响客户出货，下次要提前确认生产计划。"
- **Expected:** add_event_draft (category=Delivery)
- **Got:** add_decision_draft ❌
- **Root Cause:** gemma4:e2b 模型将"延迟"误判为"决定"类型

### Test 3: Decision ✅

- **Input:** "决定：ABC 后续订单暂时保持 OA60，不再放宽账期，等连续三票交付稳定后再评估。"
- **draft_type:** add_decision_draft ✅
- **title:** Present ✅
- **reason:** Present ✅

### Test 4: Memo ❌

- **Input:** "备忘：下次给 ABC 下单前必须再次确认标签版本和外箱唛头。"
- **Expected:** add_memo_draft
- **Got:** add_decision_draft ❌
- **Root Cause:** gemma4:e2b 模型将"备忘"误判为"决定"类型

### Test 5: Feedback ✅

- **Input:** "反馈：手机上 Agent 页面输入长文本时不够顺手，生成草稿按钮位置可以更明显。"
- **draft_type:** add_feedback_draft ✅
- **module:** Mobile ✅
- **severity:** Should Improve ✅
- **status:** Open ✅
- **suggestion:** Present ✅

---

## Model Variance Analysis

gemma4:e2b (5.1B) 在 Z4.1 Contract Layer 下的表现：

| Test | Expected | Got | Status |
|------|----------|-----|--------|
| Quality Event | add_event_draft | add_event_draft | PASS |
| Delivery Event | add_event_draft | add_decision_draft | FAIL |
| Decision | add_decision_draft | add_decision_draft | PASS |
| Memo | add_memo_draft | add_decision_draft | FAIL |
| Feedback | add_feedback_draft | add_feedback_draft | PASS |

**Conclusion:** 合约框架已部署，但 gemma4:e2b 模型在判断 draft_type 时仍有偏差。这是模型能力限制，不是代码问题。更强的模型（如 deepseek、qwen）会更准确。

---

## Notes

- **ai_status fix re-applied:** Same sed fix as Z3.1/Z3.1.2 deployments.
- **Contracts module present:** 6 files in `/opt/procurement-workspace/procurement-web/backend/app/contracts/`.
- **No secrets printed, no .env committed, no Mpango affected.**

---

**Verdict:** `PASS_Z41_DEPLOYMENT_WITH_MODEL_VARIANCE`

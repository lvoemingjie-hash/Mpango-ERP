# Procurement Workspace Pilot Deployment Result

**Date:** 2026-07-07
**Version:** 2.0.0-rc6-z4.1-contract (Z4.1 Contract Layer)
**Verdict:** READY_FOR_PILOT

---

## Deployment Info

| Item | Value |
|------|-------|
| Version | 2.0.0-rc6-z4.1-contract |
| Access URL | http://100.69.221.109:8010 (Tailscale only) |
| Backup | backups/pre-z4-1-contract-data-2026-07-07-1119.tar.gz |
| Mpango affected | NO |
| Known issues | gemma4:e2b 在 Delivery/Memo 类型判断有偏差（模型能力限制） |

---

## Pilot User Instructions

### System Purpose

系统不是替代 Excel。而是：

1. **记录重要事情** — 供应商质量事件、交付问题、关键决策
2. **保留供应商经验** — 团队共享，不因人员流动丢失
3. **减少重复整理** — AI 帮忙填写，你只需确认
4. **让 AI 帮忙** — 输入一段话，AI 自动生成结构化草稿

### How to Use

1. 打开 Agent 页面
2. 输入一段话（中文或英文）
3. 点击"生成草稿"
4. 检查 AI 生成的内容
5. 点击"确认并保存"

### What to Record

- 供应商质量问题（标签错误、货物损坏、延迟交付）
- 关键决策（账期调整、供应商评估、订单策略）
- 备忘提醒（下次下单注意事项、跟进事项）
- 使用反馈（系统哪里好用、哪里不好用）

### Feedback Channel

所有反馈通过 **Pilot Feedback** 功能提交：

1. 在 Agent 页面输入反馈内容
2. 点击"生成草稿"
3. 确认并保存

---

## Current Data Summary

| Type | Count |
|------|-------|
| Suppliers | 5 |
| Events | 12 |
| Memos | 3 |
| Decisions | 0 |
| Feedback | 1 |
| Excel Export | OK |

---

## Observation Metrics

请关注以下指标：

| # | Metric | Target |
|---|--------|--------|
| 1 | 每天是否愿意打开系统 | 用户主动使用 |
| 2 | 一次记录是否比 Excel 快 | 时间减少 |
| 3 | AI 是否减少填写时间 | 自动生成 |
| 4 | 用户是否愿意相信 AI 草稿 | 接受度高 |
| 5 | 用户修改 AI 草稿需要多少 | 修改少 |

---

## Safety Confirmation

- [x] Tailscale 私网访问
- [x] 不开放公网
- [x] 不影响 Mpango
- [x] 不改 nginx
- [x] 不改数据库结构
- [x] AI 不能删除
- [x] AI 不能批量修改
- [x] AI 不能直接写数据库
- [x] 确认保存走 Command Layer

---

**Verdict:** `READY_FOR_PILOT`

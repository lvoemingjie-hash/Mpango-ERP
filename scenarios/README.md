# Mpango ERP - Executable Business Scenarios

## Purpose
本目录包含 Mpango ERP 的**可执行业务场景定义**。

根据 `docs/workrules.md` 钢钉3的要求：
> 关键业务流程：**必须在 `/scenarios/` 下有定义**
> AI 的实现：**必须能够满足 scenario 的 Given / When / Then**
> Reviewer AI：**以 scenario 是否成立作为"是否可用"的判断依据**

## Scenario Format
所有场景使用 **Gherkin-style Given/When/Then** 格式：

```gherkin
Feature: <功能名称>
  As a <角色>
  I want <目标>
  So that <价值>

  Scenario: <场景名称>
    Given <前置条件>
    When <触发动作>
    Then <预期结果>
```

## MVP Scenarios (Phase 1)

### Authentication & Authorization
| ID | Scenario | Status | Owner |
|----|----------|--------|-------|
| SC-001 | wholesaler_login | 📝 Defined | Backend AI |
| SC-002 | create_user | 📝 Defined | Backend AI |

### Sales & Orders
| ID | Scenario | Status | Owner |
|----|----------|--------|-------|
| SC-003 | retailer_place_order | 📝 Defined | Backend AI |

## Scenario Status Legend
- 📝 Defined - 场景已定义，待实现
- 🔧 In Progress - 正在实现
- ✅ Implemented - 已实现，待验证
- ✔️ Verified - 已验证通过
- ❌ Failed - 验证失败

## Validation Rules
1. **Backend AI**: 实现必须满足所有 Given/When/Then 条件
2. **Frontend AI**: UI 必须支持场景中的用户交互
3. **Reviewer AI**: 以场景通过率作为验收标准
4. **Ops AI**: 确保场景在生产环境可执行

## Related Documents
- L0: `Multi-Tenancy Spec (MVP).md` - 多租户登录流程
- L0: `RBAC Matrix (MVP).md` - 权限控制
- L1: `Domain Workflows (MVP).md` - 业务流程定义

---

**Maintained by:** Architect AI  
**Last Updated:** 2025-01-09
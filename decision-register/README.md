# Decision Register

## Purpose
本目录记录 Mpango ERP 项目中所有**架构性、跨模块、长期影响**的关键决策。

根据 `docs/workrules.md` 的要求：
> 架构性、跨模块、长期影响的决策：**必须进入 `/decision-register/`**

## Decision Naming Convention
```
YYYY-MM-DD_<short-description>.md
```

## Decision Template
每个决策文档必须包含以下部分：
- **Decision ID**: 唯一标识符
- **Title**: 简短标题
- **Status**: 状态（Proposed / Approved / Rejected / Deprecated）
- **Context**: 背景与问题描述
- **Decision**: 具体决策内容
- **Rationale**: 决策理由
- **Alternatives Considered**: 考虑过的其他方案
- **Impact**: 影响范围与相关AI角色
- **Authority**: 权威来源（L0/L1/L2规范）
- **Implementation**: 实现细节
- **Validation**: 验证标准
- **Related Decisions**: 相关决策
- **Notes**: 补充说明

## Current Decisions

### Architecture Decisions (DR-00x)
| ID | Title | Status | Authority | Impact |
|----|-------|--------|-----------|--------|
| DR-001 | Schema-per-Tenant Multi-Tenancy Strategy | ✅ Approved | L0 Multi-Tenancy Spec | All modules |
| DR-002 | Generic CRUD Base Class with Soft Delete | ✅ Approved | L0 Database Contract | Backend |
| DR-003 | Alembic Multi-Schema Migration Strategy | ✅ Approved | L0 Database Contract | Backend, Ops |

### Implementation Decisions (2025-01-09)
| ID | Title | Status | Authority | Impact |
|----|-------|--------|-----------|--------|
| DR-2025-01-09-001 | Frontend Port Allocation: 5173 | ✅ Approved | User Requirement | Frontend, Ops |
| DR-2025-01-09-002 | Async Database Session with Tenant Isolation | ✅ Approved | L0 Multi-Tenancy Spec | Backend, Ops, All APIs |

### Product Decisions (2026-07-23)
| ID | Title | Status | Authority | Impact |
|----|-------|--------|-----------|--------|
| [DR-2026-07-23-001](2026-07-23_wholesaler-private-channel-positioning.md) | Wholesaler-Centric Private Channel Positioning | ✅ Approved | Product Owner + L0 Multi-Tenancy Spec | Product, Auth, Frontend, Tenant Onboarding, Ops |

### Governance Decisions (2026-08-25)
| ID | Title | Status | Authority | Impact |
|----|-------|--------|-----------|--------|
| [DR-2026-08-25-001](2026-08-25_harness-engineering-governance.md) | Systematic Harness Coverage and Exploratory Testing Governance | Approved | CTO + L1 Product Delivery Governance | Product, Tests, Harnesses, Review, Release Evidence |
| [DR-2026-08-25-002](2026-08-25_harness-governance-tooling-he2.md) | Machine-Validated Coverage Inventory, Debt, and Interaction Governance | Approved | CTO directive DC-12R1-MVP-L1-HE2 | CI, Product, Tests, Harnesses, Review |

## Decision Categories

### 🏗️ Architecture (架构决策)
- DR-2025-01-09-002: Async Database Session Management

### 🔧 Infrastructure (基础设施决策)
- DR-2025-01-09-001: Port Allocation

### 🔐 Security (安全决策)
- (待补充)

### 📊 Data (数据决策)
- (待补充)

### 🎨 Frontend (前端决策)
- (待补充)

### 🔌 API (接口决策)
- (待补充)

### 🧭 Product (产品决策)
- DR-2026-07-23-001: Wholesaler-Centric Private Channel Positioning

### Governance (治理决策)
- DR-2026-08-25-001: Systematic Harness Coverage and Exploratory Testing Governance
- DR-2026-08-25-002: Machine-Validated Coverage Inventory, Debt, and Interaction Governance

## Review Process
1. **提出决策**: 任何AI角色发现需要决策的事项时，创建决策文档草稿（Status: Proposed）
2. **讨论**: 在决策文档中记录讨论过程和备选方案
3. **批准**: Architect AI或Product Owner批准后，更新Status为Approved
4. **实施**: 相关AI角色按照决策实施
5. **验证**: 完成Validation清单中的所有项目

## Notes
- 所有决策必须明确引用L0/L1/L2规范作为权威来源
- 违反L0规范的决策**不允许**被批准
- 已废弃的决策保留在此目录中，Status标记为Deprecated

---

**Maintained by:** Architect AI
**Last Updated:** 2026-08-25

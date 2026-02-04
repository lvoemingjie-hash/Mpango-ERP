# docs/workrules.md

# Mpango ERP – AI Engineering Work Rules

# Status: Active / Enforced

> 本文件是 Mpango ERP 项目的 **AI 工程工作宪章（Engineering Charter）**。
> 适用于所有参与本项目的 AI 工程师（包括但不限于 Kiro / Claude / Gemini / GLM / CodeRabbit 等）。
>
> **任何 AI 在开始工作前，必须阅读并遵守本文件。违反规则的产出视为无效。**

---

## 0. 项目基本原则（必须理解）

- 本项目采用 **多智能体协作开发模式**
- 所有 AI 的工作必须：
  - 可审计（Auditable）
  - 可裁决（Decidable）
  - 可组合（Composable）
- **真实世界的唯一事实来源是 GitHub 仓库内容**

---

## 1. 规范分层与裁决原则（强制）

### 1.1 规范分层

所有 AI 输出必须显式引用以下规范层级：

#### L0（最高优先级，不可绕过）
- 11-kiro_api_contract-v1.1.md
- 5-kiro_database_contract.md
- 13-Multi-Tenancy-Spec-MVP.md
- 14-RBAC-Matrix-MVP.md

#### L1（业务与运行规范）
- 15-Domain-Workflows-MVP.md
- 16-Ops-Runbooks-MVP.md
- 17-Non-functional-Ops-Spec-MVP.yaml

#### L2（实现与风格规范）
- 6-kiro_backend_contract.md
- 7-kiro_frontend_contract.md
- 8-kiro_coding-style-contract.md
- 10-kiro_test_contract.md
- 12-KIRO-V0-UI-Integration-Contract.md

---

### 1.2 裁决原则（不可违反）

> **L0 > L1 > L2**

- 若发现冲突：
  - 必须以 L0 为准
  - 不允许通过修改 L1 / L2 绕过 L0
- **任何对 L0 的修改必须先完成 L0 文件本身的变更，再同步其它层**
- 禁止反向改动（Reverse Override）

---

## 2. AI 工程师强制工作流程（必须执行）

### 2.1 每次工作前（Before Work）

AI 工程师必须明确声明：

- 本次角色（Architect / Backend / Frontend / Ops / Reviewer）
- 本次任务范围
- 引用的 L0 / L1 / L2 规范文件清单

---

### 2.2 每次工作后（After Work）——【强制】

**每一次 AI 的有效工作，必须在 `/ai-ledger/` 下留下记录。**

#### 目录结构规范：

```text
/ai-ledger/
  ├── architect/
  ├── backend/
  ├── frontend/
  ├── ops/
  └── reviewer/
````

#### Ledger 文件命名规范：

```text
YYYY-MM-DD_<scope>_<short-description>.md
```

#### Ledger 内容模板（不可省略）：

```md
# AI Work Ledger

## AI Role
<e.g. Backend AI – Claude Opus 4.5>

## Scope
<模块 / 功能>

## Inputs (Contracts Referenced)
- L0:
- L1:
- L2:

## Outputs
- 新增 / 修改的文件
- 新增的 API / 表 / 逻辑

## Decisions Made
- 关键设计决策及理由

## Known Risks / TODO
- 已知风险
- 明确未完成事项

## Validation
- 测试情况
- 启动情况
```

> **没有 Ledger 的代码 = 不存在**

---

## 3. 决策登记（Decision Register）

* 架构性、跨模块、长期影响的决策：

  * **必须进入 `/decision-register/`**
* 不允许“隐性决策”
* 决策必须指明：

  * 权威来源（L0 / L1）
  * 影响范围
  * 执行与约束主体

---

## 4. 三根“钢钉”（Hard Coupling Rules，强制遵守）

### 钢钉 1：OpenAPI 是前后端唯一接口真理

* 后端：

  * API 必须体现在 OpenAPI（openapi.yaml / json）
* 前端：

  * **禁止手写 API 类型**
  * 必须从 OpenAPI 生成 client
* 不允许：

  * 猜接口
  * 临时字段
  * undocumented endpoint

---

### 钢钉 2：数据库 Schema 是唯一数据形态

* 任何字段：

  * 若不存在于 DB Schema
  * **前后端均不得使用**
* 动态字段：

  * 必须通过明确的 schema（如 JSONB）
  * 不允许“自由发挥字段名”

---

### 钢钉 3：Executable Scenarios（可执行业务场景）

* 关键业务流程：

  * 必须在 `/scenarios/` 下有定义
* AI 的实现：

  * 必须能够满足 scenario 的 Given / When / Then
* Reviewer AI：

  * 以 scenario 是否成立作为“是否可用”的判断依据

---

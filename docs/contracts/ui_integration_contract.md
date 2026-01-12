# KIRO-V0 UI Integration Contract (Professional Edition)

**Version:** 1.0  
**Author:** Jeff + ChatGPT  
**Purpose:** Define how V0 and KIRO cooperate to build the MPANGO ERP front-end

---

## 1. Purpose & Scope

本契约定义：
- V0 在 MPANGO ERP 项目中的作用
- V0 与 KIRO 的协作方式
- 前端代码结构与命名规范
- UI 设计系统与组件规范
- 哪些内容由 V0 负责生成，哪些内容必须由 KIRO/开发者维护
- 防止前后端耦合、逻辑污染、结构混乱

该策略是整个前端开发的统一标准，是所有 UI 设计与生成的唯一依据。

---

## 2. V0 在架构中的定位

### 2.1 明确定位：V0 = UI 设计与组件生成器

V0 用于：
- 创建 React + Tailwind UI 页面和组件
- 提供一致的设计风格
- 快速生成表单、列表、仪表盘等视觉元素
- 自动布局 UI 与交互组件

### 2.2 V0 不负责：
- ❌ API 逻辑
- ❌ 全局状态管理
- ❌ 权限系统
- ❌ 数据校验（由 backend 或 frontend schema 处理）
- ❌ 业务逻辑
- ❌ 数据转换
- ❌ 路由设计（只生成 JSX，不生成 router 结构）

所有逻辑必须留给开发者或 KIRO 处理。

---

## 3. V0 + KIRO 协作原则

### 3.1 黄金法则
- V0 负责 UI 长得怎样
- KIRO 负责 UI 怎么工作

### 3.2 协作流程（必须遵守）

**Step 1** — Jeff / KIRO 创建 UI 需求描述
```yaml
# UI Component Spec
Name: User Management Table
Type: Page + Components
Data Source: /api/v1/users
Fields:
  - name
  - email
  - role
  - status
Actions:
  - edit
  - delete
Requirements:
  - pagination
  - search bar
  - breadcrumb
```

**Step 2** — 将上面需求提交给 V0 生成 UI 代码

**Step 3** — KIRO 接收 UI 代码，补全逻辑
- API 调用（Axios / Fetch）
- 状态管理（Zustand）
- 表单验证（Zod）
- 权限控制
- 错误处理
- 业务逻辑

**Step 4** — 开发者审核与合并

---

## 4. Frontend Directory Structure Standard

```
frontend/
  src/
    components/
      ui/                 # 基础 UI（Button、Input、Card）
      domain/             # 领域组件（UserTable, RoleForm）
    pages/
      users/
      roles/
      dashboard/
    hooks/                # 自定义 hooks（useUser, useAuth）
    stores/               # Zustand stores
    services/             # API 调用
    layouts/              # 页面布局
    utils/                # 工具函数
    types/                # 类型定义
```

V0 只能输出到：
- `components/`
- `pages/`

禁止输出到其他目录。

---

## 5. Component Naming & Structure Rules

### 5.1 命名规范
- PascalCase for Components
- camelCase for functions

禁止 default export：
```typescript
export function UserTable() {}  // yes
export default function UserTable() {}  // no
```

### 5.2 组件结构规范
```typescript
import ...
export function Component() {
  return (
    <div className="">
      ...
    </div>
  );
}
```

不能生成：
- 内联样式
- 不必要的 wrapper
- 业务逻辑
- fake API 调用

---

## 6. UI Design System

### 6.1 色彩系统
- Primary: #2563eb
- Secondary: #1e293b
- Accent: #10b981
- Danger: #ef4444
- Overlay: rgba(0,0,0,0.3)

### 6.2 Spacing System
基于 Tailwind：p-4, p-6, p-8, gap-4, gap-6

### 6.3 组件规范
- Card：必须有 shadow-sm、rounded-xl
- Button：必须使用统一 variant
- Form：统一使用 grid gap-6
- Modal：必须居中、支持 ESC
- Table：必须支持分页

---

## 7. State Management Rules

前端必须使用：
- Zustand for state
- Zod for schema validation
- React Query for data fetching

V0 不能生成任何状态管理代码。

---

## 8. Error Prevention Rules

V0 禁止生成以下内容：
- ❌ 业务逻辑
- ❌ API endpoint
- ❌ 内联样式
- ❌ default export
- ❌ 状态管理
- ❌ 直接写入 router
- ❌ 数据处理
- ❌ 后端 DTO

---

## 9. Summary (给 KIRO 的关键指令)

- V0 only generates UI components.
- KIRO integrates logic and ensures architecture compliance.
- Logic must not appear in V0-generated code.
- Only two folders are allowed for V0 output:
  - src/components
  - src/pages

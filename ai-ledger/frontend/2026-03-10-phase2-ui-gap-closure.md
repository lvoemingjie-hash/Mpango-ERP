# Phase 2 补齐工作记录 — UI 间隙修复与 API 联调

**日期:** 2026-03-10  
**执行者:** AI Frontend Developer  
**目标:** 完成 MVP Phase 2 前端 UI 与后台 API 的闭环

---

## Task 1: SKU Management (商品管理页)
- **完成项**:
  - 创建了 `frontend/src/pages/skus/SKUListPage.tsx`，支持通过 `skuService.getAll` 调用后端 `GET /api/v1/skus` 获取列表。
  - 创建了 `frontend/src/pages/skus/SKUFormModal.tsx`，利用 `react-hook-form` 实现新增和编辑表单。
  - 表单通过 `skuService.create` 和 `skuService.update` 成功连接至后端接口，保存后刷新列表并弹出 Toast。
  - 更新 `AppRouter.tsx`，将 `/skus` 路由指向 `SKUListPage`。
  - 更新 `Sidebar.tsx`，在侧边栏添加 "Products" 菜单项，链接到 `/skus`。

## Task 2: 修复侧边栏路由与 404
- **完成项**:
  - **移除未实现模块**: 将 `Sidebar.tsx` 中目前缺失对应页面的 "Team" 和 "Settings" 路由予以注释隐藏，避免用户误触引发 404。
  - **顾客页面映射**:
    - 新建了 `frontend/src/services/retailerService.ts` 以调用 `GET /api/v1/retailers/bindings`。
    - 针对租户（Wholesaler）视角，新建了 `frontend/src/pages/retailers/RetailerListPage.tsx` 以展示绑定的零售商列表。
    - 修改 `AppRouter.tsx` 路由映射，将 `/retailers` 路由指向新创建的 `RetailerListPage`。
    - 将 `Sidebar.tsx` 中的 "Customers" 链接指向修正后的 `/retailers`。

## Task 3: 权限降级反馈优化
- **问题**: 在 `OrderListPage.tsx` 执行需要 `orders:update` 的操作（如 `Confirm` 等）时，如果没有权限，界面原先直接调用接口并抛出报错 Toast。
- **完成项**:
  - 用 `hasUpdatePermission` 替换过于宽泛的 `canWrite` 控制。
  - 判断逻辑：针对每个操作按钮，不仅验证订单自身状态（`canConfirm`, `canPay` 等），还将 `hasUpdatePermission` 加入 `disabled` 属性条件。
  - 当无权限时：按钮被禁用，而非被隐藏；光标呈现 `not-allowed` 状态，并加入 `title="Permission Denied"` 以向用户提供清晰的反馈。

---

*前端 Phase 2 UI 缝隙修补已执行完毕，各项补丁已基于最新后端接口和权限架构落地。*

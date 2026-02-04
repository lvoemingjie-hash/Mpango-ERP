# Mpango ERP — Frontend Contract

**Version:** 1.0
**Owner:** Jeff（Product Owner） + ChatGPT（Architect） + GLM
**Target Implementer:** Kiro Code + Future Developers
**Tech Stack:** React + Vite + TypeScript + TailwindCSS + Zustand

---

## 1. 技术栈要求

### 1.1 核心技术
- **框架：** React 18+
- **构建工具：** Vite
- **语言：** TypeScript
- **样式：** TailwindCSS
- **状态管理：** Zustand
- **HTTP 客户端：** Axios
- **路由：** React Router v6
- **表单：** React Hook Form + Zod
- **UI 组件：** Headless UI / Radix UI

### 1.2 开发工具
- **代码格式化：** Prettier
- **代码检查：** ESLint
- **类型检查：** TypeScript
- **测试：** Vitest + React Testing Library

## 2. 目录结构

```
frontend/
├── public/
├── src/
│   ├── components/          # 组件目录
│   │   ├── ui/             # 基础 UI 组件
│   │   ├── forms/          # 表单组件
│   │   └── layout/         # 布局组件
│   ├── pages/              # 页面组件
│   ├── hooks/              # 自定义 Hooks
│   ├── services/           # API 服务
│   ├── stores/             # Zustand 状态管理
│   ├── types/              # TypeScript 类型定义
│   ├── utils/              # 工具函数
│   ├── router/             # 路由配置
│   ├── assets/             # 静态资源
│   ├── styles/             # 全局样式
│   ├── App.tsx             # 根组件
│   └── main.tsx            # 入口文件
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── .eslintrc.js
├── .prettierrc
└── README.md
```

## 3. API 交互规范

- **必须** 使用统一的 API 客户端
- **必须** 实现请求/响应拦截器
- **必须** 按模块组织 API 服务
- **必须** 处理认证和错误
- **默认端口**: 5173 (避免3000端口冲突)

## 4. 强制要求

1. **所有组件** 必须使用 TypeScript
2. **所有样式** 必须使用 TailwindCSS
3. **所有状态** 必须通过 Zustand 管理
4. **所有表单** 必须使用 React Hook Form + Zod
5. **所有 API** 必须通过统一的服务层调用

---

**重要提醒：** Kiro 必须严格遵循此规范，确保前端代码的一致性和可维护性。

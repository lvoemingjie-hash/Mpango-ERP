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

### 2.1 根目录结构
```
frontend/
├── public/
│   ├── favicon.ico
│   └── index.html
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

### 2.2 强制要求
- **必须** 按功能模块组织代码
- **必须** 使用 TypeScript
- **必须** 遵循命名规范

## 3. API 交互规范

### 3.1 Axios 封装 (`services/api.ts`)
```typescript
import axios, { AxiosResponse, AxiosError } from 'axios';

// 创建 axios 实例
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data;
  },
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
```

### 3.2 API 服务模块化
```typescript
// services/userService.ts
import api from './api';
import { User, CreateUserDTO, UpdateUserDTO } from '../types/user';

export const userService = {
  getUsers: (page: number = 1, size: number = 10) =>
    api.get<User[]>(`/users?page=${page}&size=${size}`),

  getUserById: (id: number) =>
    api.get<User>(`/users/${id}`),

  createUser: (userData: CreateUserDTO) =>
    api.post<User>('/users', userData),

  updateUser: (id: number, userData: UpdateUserDTO) =>
    api.put<User>(`/users/${id}`, userData),

  deleteUser: (id: number) =>
    api.delete(`/users/${id}`),
};
```

### 3.3 要求
- **必须** 使用统一的 API 客户端
- **必须** 实现请求/响应拦截器
- **必须** 按模块组织 API 服务
- **必须** 处理认证和错误

## 4. 组件规范

### 4.1 组件结构
```typescript
// components/ui/Button.tsx
import React from 'react';
import { cn } from '../../utils/cn';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  className,
  children,
  disabled,
  ...props
}) => {
  const baseClasses = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2';

  const variantClasses = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500',
    secondary: 'bg-gray-200 text-gray-900 hover:bg-gray-300 focus:ring-gray-500',
    danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  };

  const sizeClasses = {
    sm: 'px-3 py-2 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg',
  };

  return (
    <button
      className={cn(
        baseClasses,
        variantClasses[variant],
        sizeClasses[size],
        (disabled || loading) && 'opacity-50 cursor-not-allowed',
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg className="animate-spin -ml-1 mr-3 h-5 w-5" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {children}
    </button>
  );
};
```

### 4.2 组件要求
- **必须** 使用 TypeScript
- **必须** 定义 Props 接口
- **必须** 使用 TailwindCSS
- **必须** 支持 className 传递
- **必须** 遵循原子设计原则

## 5. 页面结构

### 5.1 页面组件示例
```typescript
// pages/Users/UserList.tsx
import React, { useEffect } from 'react';
import { Button } from '../../components/ui/Button';
import { useUserStore } from '../../stores/userStore';
import { UserTable } from './components/UserTable';

export const UserListPage: React.FC = () => {
  const { users, loading, error, fetchUsers, deleteUser } = useUserStore();

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleDelete = async (id: number) => {
    if (window.confirm('确定要删除这个用户吗？')) {
      await deleteUser(id);
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center h-64">加载中...</div>;
  }

  if (error) {
    return <div className="text-red-600 text-center">错误: {error}</div>;
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">用户管理</h1>
        <Button onClick={() => navigate('/users/create')}>
          添加用户
        </Button>
      </div>

      <UserTable
        users={users}
        onDelete={handleDelete}
      />
    </div>
  );
};
```

### 5.2 页面要求
- **必须** 包含错误处理
- **必须** 包含加载状态
- **必须** 使用状态管理
- **必须** 响应式设计

## 6. 路由配置

### 6.1 路由定义 (`router/index.tsx`)
```typescript
import { createBrowserRouter } from 'react-router-dom';
import { Layout } from '../components/layout/Layout';
import { LoginPage } from '../pages/Auth/LoginPage';
import { UserListPage } from '../pages/Users/UserListPage';
import { UserCreatePage } from '../pages/Users/UserCreatePage';
import { ProtectedRoute } from '../components/auth/ProtectedRoute';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <div>Dashboard</div>,
      },
      {
        path: 'users',
        children: [
          {
            index: true,
            element: <UserListPage />,
          },
          {
            path: 'create',
            element: <UserCreatePage />,
          },
        ],
      },
    ],
  },
]);
```

### 6.2 路由要求
- **必须** 集中管理路由
- **必须** 实现路由守卫
- **必须** 支持嵌套路由
- **必须** 处理 404 页面

## 7. 状态管理

### 7.1 Zustand Store 示例
```typescript
// stores/userStore.ts
import { create } from 'zustand';
import { userService } from '../services/userService';
import { User, CreateUserDTO } from '../types/user';

interface UserState {
  users: User[];
  loading: boolean;
  error: string | null;
  fetchUsers: () => Promise<void>;
  createUser: (userData: CreateUserDTO) => Promise<void>;
  deleteUser: (id: number) => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  users: [],
  loading: false,
  error: null,

  fetchUsers: async () => {
    set({ loading: true, error: null });
    try {
      const response = await userService.getUsers();
      set({ users: response.data.items, loading: false });
    } catch (error) {
      set({ error: '获取用户列表失败', loading: false });
    }
  },

  createUser: async (userData) => {
    set({ loading: true, error: null });
    try {
      await userService.createUser(userData);
      await get().fetchUsers(); // 重新获取列表
    } catch (error) {
      set({ error: '创建用户失败', loading: false });
    }
  },

  deleteUser: async (id) => {
    set({ loading: true, error: null });
    try {
      await userService.deleteUser(id);
      set(state => ({
        users: state.users.filter(user => user.id !== id),
        loading: false
      }));
    } catch (error) {
      set({ error: '删除用户失败', loading: false });
    }
  },
}));
```

### 7.2 状态管理要求
- **必须** 使用 Zustand
- **必须** 按功能模块分离 Store
- **必须** 处理异步操作
- **必须** 包含错误状态

## 8. 类型定义

### 8.1 类型文件结构
```typescript
// types/user.ts
export interface User {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  created_at: string;
  updated_at?: string;
}

export interface CreateUserDTO {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

export interface UpdateUserDTO {
  email?: string;
  full_name?: string;
}

// types/api.ts
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message: string;
  timestamp: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: {
    page: number;
    size: number;
    total: number;
    pages: number;
  };
}
```

### 8.2 类型要求
- **必须** 定义所有接口类型
- **必须** 按模块组织类型
- **必须** 与后端 DTO 保持一致
- **必须** 使用泛型提高复用性

## 9. 表单处理

### 9.1 表单组件示例
```typescript
// components/forms/UserForm.tsx
import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

const userSchema = z.object({
  username: z.string().min(3, '用户名至少3个字符'),
  email: z.string().email('请输入有效的邮箱地址'),
  password: z.string().min(8, '密码至少8个字符'),
  full_name: z.string().optional(),
});

type UserFormData = z.infer<typeof userSchema>;

interface UserFormProps {
  onSubmit: (data: UserFormData) => Promise<void>;
  loading?: boolean;
}

export const UserForm: React.FC<UserFormProps> = ({ onSubmit, loading }) => {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<UserFormData>({
    resolver: zodResolver(userSchema),
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <Input
        label="用户名"
        {...register('username')}
        error={errors.username?.message}
      />

      <Input
        label="邮箱"
        type="email"
        {...register('email')}
        error={errors.email?.message}
      />

      <Input
        label="密码"
        type="password"
        {...register('password')}
        error={errors.password?.message}
      />

      <Input
        label="姓名"
        {...register('full_name')}
        error={errors.full_name?.message}
      />

      <Button type="submit" loading={loading}>
        提交
      </Button>
    </form>
  );
};
```

### 9.2 表单要求
- **必须** 使用 React Hook Form
- **必须** 使用 Zod 进行验证
- **必须** 显示验证错误
- **必须** 处理提交状态

## 10. 样式规范

### 10.1 TailwindCSS 配置
```javascript
// tailwind.config.js
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
      },
    },
  },
  plugins: [],
};
```

### 10.2 样式要求
- **必须** 使用 TailwindCSS
- **必须** 定义设计系统颜色
- **必须** 响应式设计
- **禁止** 内联样式

## 11. 代码质量

### 11.1 ESLint 配置
```javascript
// .eslintrc.js
module.exports = {
  extends: [
    '@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
  ],
  rules: {
    'react/react-in-jsx-scope': 'off',
    '@typescript-eslint/no-unused-vars': 'error',
    'react-hooks/exhaustive-deps': 'warn',
  },
};
```

### 11.2 质量要求
- **必须** 通过 ESLint 检查
- **必须** 使用 Prettier 格式化
- **必须** 无 TypeScript 错误
- **必须** 遵循 React 最佳实践

## 12. 强制要求

1. **所有组件** 必须使用 TypeScript
2. **所有样式** 必须使用 TailwindCSS
3. **所有状态** 必须通过 Zustand 管理
4. **所有表单** 必须使用 React Hook Form + Zod
5. **所有 API** 必须通过统一的服务层调用

---

**重要提醒：** Kiro 必须严格遵循此规范，确保前端代码的一致性和可维护性。

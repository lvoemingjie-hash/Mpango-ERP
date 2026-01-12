# Mpango ERP — Coding Style Contract
**Version:** 1.1  
**Purpose:** 定义帝国工匠的行为准则，确保代码质量、可维护性，并最大化 AI 辅助开发效率。  
**Last Updated:** 2025-06-10

## 1. 总体原则

我们的代码是帝国的基石。每一行代码都必须清晰、一致、经得起时间的考验。

- **可读性第一**: 代码首先是写给人读的，其次才是给机器执行的。
- **一致性强制**: 团队中的所有代码必须看起来像出自一人之手。工具（Formatter, Linter）是强制执行一致性的"宪兵"。
- **AI 友好性**: 编写的代码和注释应结构清晰，以便 AI 工具（如 `CodeWhisperer`）能够更好地理解和生成。
- **质量内建**: 质量检查（Lint, Type Check）是本地开发流程的一部分，而不是 CI 的补救措施。

---

## 2. 后端

### 2.1. 技术栈与工具链
- **Language**: Python >= 3.11.
- **Formatter**: **Black** (line-length 88). **所有提交的代码必须经过 Black 格式化。**
- **Linter**: **Ruff**. **所有提交的代码必须通过 `ruff check`。**
- **Type Checking**: **Mypy**. **所有新代码必须包含类型注解，并通过 `mypy` 检查。**
- **Testing**: `pytest` + `pytest-asyncio`.
- **Dependencies**: 使用 **Poetry** 进行管理，`poetry.lock` 必须提交到版本库。

### 2.2. AI 辅助开发
- **AI 工具**: **Amazon CodeWhisperer**.
- **使用原则**:
    - 鼓励使用 CodeWhisperer 生成样板代码、函数体和测试用例。
    - **AI 生成的代码，必须像人工编写的代码一样，通过 `Black`, `Ruff`, `Mypy` 的检查。**
    - 开发者对 AI 生成的代码负有最终责任，必须审查其逻辑和安全性。

### 2.3. 编码规范
- **Docstring**: 使用 Google Style，为所有公共模块、类和函数编写清晰的文档字符串。
- **命名**: 遵循 PEP 8，使用 `snake_case`。
- **导入**: 使用 `isort`（集成在 Ruff 中）对导入进行排序。

---

## 3. 前端

### 3.1. 技术栈与工具链
- **Language**: **TypeScript** with strict mode ON.
- **Formatter**: **Prettier**.
- **Linter**: **ESLint** (集成 Prettier 插件).
- **Testing**: `Vitest` for unit tests, `Playwright` for E2E tests.
- **CSS**: **Tailwind CSS**. 优先使用 Utility Classes，避免内联样式。

### 3.2. AI 辅助开发
- **AI 工具**: **Amazon CodeWhisperer**.
- **使用原则**:
    - 鼓励使用 CodeWhisperer 生成组件、类型定义和测试。
    - **AI 生成的代码，必须通过 `ESLint` 和 `TypeScript` 编译器的检查。**
    - 严禁使用 `any` 类型，除非有明确的 `// TODO: refine this type` 注释。

### 3.3. 编码规范
- **组件命名**: 组件名使用 `PascalCase`，文件名使用 `kebab-case`。
- **文件结构**: 按功能或页面组织组件，保持目录结构清晰。

---

## 4. Git 与协作契约

### 4.1. 分支策略
- `main`: 生产环境分支，受保护。
- `develop`: 开发集成分支。
- `feature/*`: 新功能开发分支。
- `hotfix/*`: 紧急修复分支。

### 4.2. 提交信息
- **强制规范**: 使用 **Conventional Commits** 规范 (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- **目的**: 使提交历史清晰可读，并支持自动化生成 Changelog。

### 4.3. Pull Request (PR) 流程
1.  **创建 PR**: 从 `feature/*` 向 `develop`，或从 `develop`/`hotfix/*` 向 `main` 提交 PR。
2.  **PR 描述**: 必须清晰描述 **What (做了什么)**, **Why (为什么做)**, **How (怎么做的)**, 以及 **Testing Steps (如何测试)**。
3.  **自动化检查**:
    - **CI 必须通过**: 所有 Lint, Type Check, Test 必须通过。
    - **AI 审查者**: `Amazon DevOps Guru for Code` 必须给出"非高危"预测。
4.  **人工审查**:
    - **至少需要一名工程师的 Approval**。
    - 审查者重点关注业务逻辑、架构设计和安全性。
5.  **合并**: 只有在所有检查和审查通过后，方可合并。

---

## 5. 文档契约

- **项目根 `README.md`**: 必须包含项目简介、快速启动、开发指南、部署指南以及指向所有核心契约的链接。
- **模块 `README.md`**: 每个核心业务模块（如 `inventory`, `sales`）文件夹内，必须有一个 `README.md`，说明其职责、公共 API 和关键设计决策。
- **代码即文档**: 清晰的变量名、函数名和 Docstring 是文档的第一道防线。

---

## 6. 附录：工具配置示例

> **注意**: 以下为配置示例，具体版本号请以项目实际为准。

### `pyproject.toml` (Backend)

```toml
[tool.black]
line-length = 88
[tool.ruff]
line-length = 88
select = [
    "E",  # pycodestyle errors
    "W",  # pycodestyle warnings
    "F",  # pyflakes
    "I",  # isort
    "UP", # pyupgrade (替代无效的 "N")
    "B",  # flake8-bugbear
    "C90", # mccabe complexity
]
ignore = ["E501", "B008"]
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```


### `.eslintrc.cjs` (Frontend)
```javascript
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    '@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
  },
};
```

---

## 7. Changelog

### v1.1 (2025-06-10)
- **战略重构**: 将"风格指南"升级为"编码契约"，注入总体原则和哲学。
- **AI 融入**: 明确 `Amazon CodeWhisperer` 的使用原则和责任归属。
- **流程对齐**: 将 Git/PR 流程与 `CI/CD` 契约中的 AI 审查者对齐。
- **增强可操作性**: 增加附录，提供 `pyproject.toml` 和 `.eslintrc.cjs` 的配置示例。

### v1.0 (2025-06-10)
- Initial draft with basic Python/React style guidelines.

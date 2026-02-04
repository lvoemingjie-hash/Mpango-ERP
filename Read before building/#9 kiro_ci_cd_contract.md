# Mpango ERP — CI/CD Contract
**Version:** 1.1
**Purpose:** 定义帝国自动化兵工厂的构建、测试、部署策略与质量门槛，并融入 AI 审查机制。
**Last Updated:** 2025-06-10

## 1. 总体原则

- **自动化优先**: 所有可重复的流程，都必须自动化。
- **质量内建**: 质量是构建出来的，不是测试出来的。每个环节都设有质量门槛。
- **安全左移**: 安全检查和合规性，必须在开发流程的最早阶段介入。
- **AI 赋能**: 利用 AI 工具增强代码审查、风险预测和运维效率。

---

## 2. 当前阶段：GitHub Actions + AI 审查者

当前，我们使用 GitHub Actions 作为 CI/CD 引擎，并集成 AI 服务作为强制审查环节。

### 2.1. 触发条件
- **Push to `develop`**: 触发完整的 CI 流程（测试、构建、部署到 Staging）。
- **Pull Request to `main`**: 触发完整的 CI 流程，所有检查通过后方可合并。
- **Push to `main`**: 触发完整的 CI 流程，并自动部署到 Staging。

### 2.2. CI 流程
1.  **代码审查阶段**:
    - **AI 辅助审查**: 强制运行 `Amazon CodeWhisperer` 的代码建议检查，为人类审查者提供优化建议。
    - **AI 风险预测**: 强制运行 `Amazon DevOps Guru for Code`，对代码变更进行未来风险预测。**任何“高危”预测都将导致 CI 失败**。
2.  **质量检查阶段**:
    - **Lint**: `ruff check` (backend), `ESLint` (frontend).
    - **Type Check**: `mypy` (backend).
    - **单元测试**: `pytest` with coverage.
3.  **构建阶段**:
    - **Backend**: 构建 Docker Image 并推送到镜像仓库。
    - **Frontend**: `npm build` 生成静态资源。
4.  **集成测试阶段**:
    - 启动完整的依赖环境（如 `docker-compose -f docker-compose.test.yml up`）。
    - 运行端到端的 API 测试。
5.  **部署阶段**:
    - **Deploy to Staging**: 自动部署到 Staging 环境。
    - **Smoke Test**: 部署后自动运行冒烟测试，确保服务可用。

### 2.3. 必须通过的质量门槛
- **单元测试覆盖率**: Backend >= 85%。
- **代码质量**: `ruff`, `ESLint`, `mypy` 0 errors, 0 warnings。
- **AI 风险预测**: `DevOps Guru for Code` 无“高危”预测。
- **构建成功**: Backend Docker Image 和 Frontend build 必须成功。

---

## 3. 下一阶段：迁移至 AWS CodePipeline

为获得与 AWS 服务（如 Fargate, Aurora）更深的集成和更强的控制力，我们的下一阶段目标是迁移至 AWS 原生 CI/CD。

### 3.1. 目标架构
- **Source**: GitHub Webhook.
- **CI**: AWS CodeBuild (负责构建、测试).
- **CD**: AWS CodePipeline (负责编排、部署).
- **Deploy**: AWS Fargate / ECS.

### 3.2. 迁移收益
- **无缝集成**: 与 AWS IAM、IRSA 深度集成，实现更安全的部署。
- **成本优化**: 按构建时间计费，无需维护自托管 Runner。
- **统一管控**: 所有基础设施和部署流程在 AWS 控制台内统一管理。

---

## 4. 部署与安全策略

### 4.1. 环境管理
- **Staging**: 自动部署，用于功能验证和集成测试。
- **Production**: 手动审批部署。通过 GitHub 的 Protected Branch 或 CodePipeline 的 Manual Approval Step 控制。

### 4.2. Secrets 管理
- **原则**: 绝不将任何密钥（`.env` 文件）提交到版本库。
- **当前**: 使用 GitHub Secrets 管理不同环境的变量（如 `STAGING_DATABASE_URL`）。
- **未来**: 迁移到 AWS Secrets Manager，并通过 IRSA 授权给 Fargate 任务。

### 4.3. 生产部署安全标准
- **强制要求**: 生产环境的部署**必须**使用 **IAM Roles for Service Accounts (IRSA)**。
- **禁止**: 在容器环境变量或 EC2 实例角色中硬编码任何 AWS 访问密钥。

---

## 5. 回滚与通知

### 5.1. 回滚计划
- **版本化**: 每次部署必须生成唯一的、不可变的 Image Tag (e.g., `v1.2.3-commit-sha`)。
- **回滚操作**: 如需回滚，部署上一个稳定版本的 Image Tag，并自动执行 Smoke Test。

### 5.2. 通知策略
- **失败必告**: 任何 CI/CD 环节失败，**必须**发送通知到指定频道（如 Slack `#dev-alerts`）。
- **部署通知**: 生产环境部署成功/失败，必须发送通知。

---

## 6. 未来演进路径

- **当前**: GitHub Actions + AI 审查者。
- **中期**: 全面迁移至 **AWS CodePipeline**，实现云原生 CI/CD。
- **最终**: 迈向 **AWS Agents for DevOps**，实现“意图驱动”的部署。当主将下达“部署新版本”指令时，AI Agent 将自动完成从风险分析、蓝绿部署到监控告警的全过程。

---

## 7. 附录：当前 GitHub Actions 示例

> **注意**: 此附录仅供参考，具体实现应遵循上述契约规范。
```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  # A placeholder for your main jobs (lint, test, build, etc.)
  # This ensures the YAML structure is valid.
  main-ci:
    runs-on: ubuntu-latest
    steps:
      - name: A placeholder step
        run: echo "This is where your main CI jobs would run."

  notify-on-failure:
    if: failure()
    needs: [main-ci] # Depends on the main job
    runs-on: ubuntu-latest
    steps:
      - name: Notify Slack on Failure
        uses: 8398a7/action-slack@v3
        with:
          status: failure
          channel: '#dev-alerts'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}

```

---

## 8. Changelog

### v1.1 (2025-06-10)
- **战略升级**: 引入 AI 审查者 (`CodeWhisperer`, `DevOps Guru for Code`)，赋予其强制检查权。
- **结构重组**: 明确区分“当前阶段”和“下一阶段”，为迁移 AWS CodePipeline 指明方向。
- **安全强化**: 将 `IRSA` 设为生产部署的强制安全标准。
- **规范整合**: 将具体实现代码移至附录，保持主体契约的清晰和权威。

### v1.0 (2025-06-10)
- Initial draft based on GitHub Actions workflow.

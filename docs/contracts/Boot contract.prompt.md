# Boot Contract.prompt.md

本文件是 Boot Contract 的精简版，用于 AI、代码审查和设计评审时的快速对齐，不替代完整文本。

## 要点

- **身份认证与租户边界**：所有请求范围状态（auth, tenant, identity）必须仅在 context 模块中定义；middleware 和 dependencies 只能读取 context，不能定义 auth 状态。
- **权限控制 / RBAC**：导入图方向：api.context → api.middleware → api.dependencies → api.v1；禁止向上或横向导入；循环导入视为契约违反。
- **数据安全与日志**：避免日志输出密码、token、密钥等敏感字段；OPS 负责环境变量和密钥管理。
- **部署与运维约束**：Boot 成功定义仅在干净非 Docker 本地环境通过 poetry run uvicorn main:app + curl /health；Docker 仅为打包层，不能修复缺失依赖或掩盖循环导入。
- **OPS 责任**：OPS 负责环境变量、秘密、网络端口、健康检查、容器生命周期；不得修改 Python 导入结构或绕过启动失败。
- **AI 工作规则**：AI 必须先读取 boot_contract.md 和 architecture_constitution.md，并在 AI Ledger 中声明“Boot Contract acknowledged”。
- **证据要求**：任何“修复”或“工作”声明必须包含完整命令和原始输出；截图、总结或释义不可接受。
- **违反处理**：检测到违反时，所有部署停止，违规变更必须撤销，并在此契约内进行纠正；无例外过程。
- **最终权威**：冲突时，Architecture Constitution > Boot Contract > 所有其他契约、规范、测试或实现。
- **版本命名**：vX.Y.Z-rcN 为普通候选版本；vX.Y.Z-rcN-boot-validated 为已按 Boot Contract L0.5 完成 checklist 检查的版本。

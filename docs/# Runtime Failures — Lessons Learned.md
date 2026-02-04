# Runtime Failures — Lessons Learned

可以看到整个话题是从“请指导我在本地用 docker 部署一个本地项目”开始，到现在已经完成了 backend 的 Docker 启动和 `/health` 联调闭环。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/56dd4c70-63da-4d94-8877-3e86311391cb/DEPLOYMENT_STATUS_INDEX.md)

## 部署失败的过程

- 起点：你希望在本地用 Docker 部署一个已有的 ERP backend 项目，自己不改业务代码，但能让服务跑起来并可从浏览器访问。 [chatgpt](https://chatgpt.com/c/68f84329-f438-8322-8239-7f77786df564)
- 关键困难：
  - 早期 backend 存在循环依赖与启动失败（`api.dependencies` 与 `api.middleware.rbac`），以及 Docker 中找不到 `uvicorn`、虚拟环境损坏等问题。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/3ff87702-6a3c-4975-86ea-b174d0f9791c/Dockerfile)
  - 多轮 AI 修复容易“越修越乱”，ledger 经常宣称已修复但缺乏可验证证据。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/5cf42be4-41c4-481e-9b34-265b8bd86cdb/2026-01-20_boot_contract_alignment.md)

- 你的结构化解决方案：
  - 制定 **Boot Contract**：强制以 `poetry run uvicorn main:app` 和 `/health` 200 作为唯一启动标准（本地 & Docker）； [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/d25c8c63-ea16-4def-adb4-544f911f5264/Boot-contract.md)
  - 引入 **PLAN / EXECUTION / EVIDENCE** 三段式 AI ledger 规范，并对 Backend AI / Ops AI 分工约束； [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/1046968f-1625-4049-97b5-04cab337302d/2026-01-20_ops_boot_contract_verification.md)
  - 新增 `Boot-contract.md`、`2026-01-20_boot_contract_alignment.md`、`2026-01-20_ops_boot_contract_verification.md` 等文档，将责任和证据写清楚。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/06c5e558-75f9-4695-9f5f-2b36ca198fc7/2026-01-20_ops_boot_contract_verification.md)

- Backend AI 结果：
  - 在本地裸环境下，backend 已能通过 `poetry run uvicorn main:app` 启动，`/health` 返回 `{"status":"healthy","service":"mpango-erp-backend","version":"0.1.0",...}`。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/1046968f-1625-4049-97b5-04cab337302d/2026-01-20_ops_boot_contract_verification.md)

- Ops AI 结果：
  - 识别出 Docker 失败原因为 **(c) ops packaging error**：Windows `.venv` / `.pyd` 被带入 Linux 镜像并在运行时被卷挂载破坏； [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/1046968f-1625-4049-97b5-04cab337302d/2026-01-20_ops_boot_contract_verification.md)
  - 修复手段包括：为 backend 增加 `.dockerignore` 排除 `.venv` 等文件，并在 Dockerfile 中使用 `poetry install --no-root --no-interaction --no-ansi --no-cache` 重新安装容器内依赖； [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/3ff87702-6a3c-4975-86ea-b174d0f9791c/Dockerfile)
  - 重新 build + up 后，`mpango_backend` 在 Docker 中正常启动，健康检查 200，与本地行为一致。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/06c5e558-75f9-4695-9f5f-2b36ca198fc7/2026-01-20_ops_boot_contract_verification.md)

- 当前状态：
  - 你在本机执行 `docker compose down -v` → `docker compose build backend` → `docker compose up backend` → `Invoke-WebRequest /health`，确认 StatusCode 200，JSON 返回健康信息，说明 **本地 Docker 部署已成功、Boot Contract v1 闭环完成**。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/06c5e558-75f9-4695-9f5f-2b36ca198fc7/2026-01-20_ops_boot_contract_verification.md)
  - 已为这次链路编写了一段可直接写入 `DEPLOYMENT_STATUS_INDEX.md` 的里程碑记录，标记为“2026-01-20 – Boot Contract v1 闭环完成”。 [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/56dd4c70-63da-4d94-8877-3e86311391cb/DEPLOYMENT_STATUS_INDEX.md)

下次会话可以在这个基础上继续做两类事：

- 产品侧：继续打磨 ERP 的 PRD / 模块、或开始整理成 Spec-Kit / OpenAPI 规范； [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/125624917/9458a5a1-23de-459f-8d68-d070a9c87d8f/2026-01-20_auth_tenant_context_layering.md)
- 工程侧：创建管理员账号、访问前端 / Swagger，并开始为后续模块开发定义新的 Boot Contract 与测试脚本。
## 1. 为什么之前的测试都没发现这个问题

- 之前的验证更多停留在“功能层面”和“接口是否能跑通”，而没有针对 **应用启动过程、模块加载顺序** 做系统性的检查（例如在全量依赖注入、开启中间件链路后的冷启动测试）。
- 测试环境中的调用路径相对单一，没有覆盖到「RBAC 中间件 + FastAPI Dependencies + 多租户上下文」同时参与的完整调用链，因此隐藏的循环依赖没有被触发。
- 过于信任“单文件/小范围改动后仍能启动”的经验判断，没有把 **`docker compose up backend` + `/health` 冷启动通过** 视为每次结构性调整后的强制性验收项。

## 2. Boot Contract 起到了什么作用

- Boot Contract 把“系统能正常冷启动并通过基础健康检查”上升为一条 **硬约束**，而不是“顺便跑一下就好”的检查，这迫使整个架构必须面对并消除结构性问题（例如循环依赖），而不能靠局部 workaround 糊过去。
- 它清晰地定义了最小可接受行为：`docker compose up backend` 必须成功、`/health` 必须返回 200、不能有 ImportError / 循环导入，这相当于为“是否允许继续在此基础上开发”设定了一道 **最低生产质量门槛**。
- 对 AI / 人类协作来说，Boot Contract 也是一个“**防守型边界**”：任何让系统连启动都失败的修改，都是不可接受的，这让后续所有任务（功能扩展、性能优化）都有了一个安全、稳定的起点。

## 3. 哪些错误是“AI 必然会犯的”

- AI 在大规模重构时，很容易“看起来分层正确，但在 Python 导入层级上制造循环依赖”，例如让 `middleware` 反向依赖 `dependencies`，或者在 `dependencies.py` 里访问 DB / 解码 JWT，导致初始化阶段加载顺序错乱。
- AI 倾向于在一个文件里“顺手引用现成的工具函数或模型”，而不自觉地打破原本设计好的 **依赖方向**（如 context → middleware → dependencies → routes），这种“局部最优”的写法在短期看起来方便，但中长期几乎必然演化成难以排查的结构性问题。
- 在没有明确 Boot Contract 和架构约束的情况下，AI 会不断累积“隐形技术债”：例如把认证逻辑塞进依赖、让中间件直接访问数据库、在启动阶段做过重的初始化，这些做法在人类肉眼 review 时不一定立刻显错，但在生产环境下非常容易演变成无法启动或难以扩展的系统。

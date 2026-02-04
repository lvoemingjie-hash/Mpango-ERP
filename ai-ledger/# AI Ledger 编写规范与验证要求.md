# AI Ledger 编写规范与验证要求

**目的**
本规范用于约束所有 AI（Backend AI、OPS AI 等）在编写和更新 ai-ledger / 说明文档时的行为，防止只写“自以为正确的总结”，而不提供可验证的证据。

---

## 一、Ledger 结构必须包含的三个区块

每一条较大的改动或“修复”记录，必须严格分成三个部分：

1. **PLAN（计划）**
   - 说明：你 _打算_ 做什么、为什么要这样做。
   - 内容示例：
     - 修改哪些模块（文件/目录）
     - 预期要解决的问题（例如：循环依赖、性能瓶颈、安全隐患）
     - 预期的成功标准（例如：`/health` 返回 200，无 ImportError）

2. **EXECUTION（执行）**
   - 说明：你 **实际** 做了什么，而不是你觉得自己做了什么。
   - 必须包含：
     - 修改过的文件路径列表
     - 关键代码片段或 `git diff` 摘要（不要只写“已优化逻辑”）
     - 实际执行过的命令（包含完整参数），例如：
       - `poetry install --no-root --no-ansi`
       - `poetry run uvicorn main:app --host 0.0.0.0 --port 8000`
       - `docker compose build backend`
       - `docker compose up backend`

3. **EVIDENCE（证据）**
   - 说明：用**原始输出**证明你的改动真的生效，而不是用概括性语言。
   - 必须包含：
     - 关键终端输出片段（例如 `/health` 返回 200 的 curl 输出）
     - 关键日志片段（例如 backend 启动日志中 “Uvicorn running on http://0.0.0.0:8000”）
     - 若失败，必须贴出失败的完整报错（ImportError、Traceback、`Command not found: uvicorn` 等）

> 只有 EVIDENCE 区块中的内容才能视为“事实”，PLAN 和 EXECUTION 只代表 AI 的意图与操作说明。

---

## 二、禁止的 Ledger 写法（反例）

以下写法在 Ledger 中是 **不被接受的**：

- “已修复循环依赖问题。”
- “docker compose up backend 现在可以正常运行。”
- “/health 已经返回 200。”

如果没有附上：

- 实际运行的命令；以及
- 对应的命令输出原文；

一律视为“未提供证据”。

---

## 三、针对 Backend 服务的强制验证要求

对于涉及 backend 服务（FastAPI / Uvicorn）的任何“修复”，Ledger 中必须包含以下验证步骤及其输出：

1. **本地运行验证（非 Docker 环境）**

   ```bash
   cd backend
   poetry install --no-root --no-interaction --no-ansi
   poetry run uvicorn main:app --host 0.0.0.0 --port 8000
EVIDENCE 必须包含：

Uvicorn 启动成功日志的关键行：

例如：Uvicorn running on http://0.0.0.0:8000

如果启动失败，必须贴出完整 Traceback。

/health 健康检查

在服务成功启动后执行：

bash
curl -f http://localhost:8000/health
EVIDENCE 必须包含：

成功时的 HTTP 状态行或返回体（例如 {"status":"ok"}）。

如果失败（非 2xx），必须贴出 curl 的错误输出。

Docker Compose 环境验证

在项目根目录执行：

bash
docker compose build backend
docker compose up backend
EVIDENCE 必须包含：

docker compose logs backend 中 uvicorn 启动的关键行；

若有错误（例如 Command not found: uvicorn、ImportError），必须原样贴出。

四、针对“循环依赖”修复的专门要求
当 Ledger 声称“已修复循环依赖（例如 api.dependencies 与 api.middleware.rbac 之间）”时，除了上述通用要求外，还必须：

在 EXECUTION 中列出：

修改过的文件：

backend/api/context/auth.py

backend/api/context/tenant.py

backend/api/middleware/auth.py

backend/api/middleware/rbac.py

backend/api/dependencies.py

backend/main.py

每个文件中的关键接口/类的当前定义（至少贴出核心函数签名与注释）。

在 EVIDENCE 中增加：

一个 Python 导入测试脚本（或者交互式输出），确认以下导入顺序不会抛出 ImportError 或循环引用：

python
import api.context
import api.middleware.auth
import api.middleware.rbac
import api.dependencies
五、决策与回滚信息
对于重大结构调整（例如 auth/tenant context 重构、Dockerfile 变更），Ledger 还必须记录：

原始问题描述（含原始错误日志），例如：

ImportError: cannot import name 'get_current_user_context' from 'api.dependencies'

Command not found: uvicorn

所采用的方案与被放弃的替代方案（若有）。

若后续发现该改动引入新的问题，必须在新的 Ledger 条目中引用原条目的 ID，并说明回滚或修正策略。

六、审核人与最终验收
人类 Owner（Jeff） 或上层系统只能依据 EVIDENCE 区块进行验收。

如果 EVIDENCE 中没有真实命令和日志输出，即使 PLAN 与 EXECUTION 写得再完美，也视为“未通过审核”。

总之：不看你说了什么，看你“跑过什么命令、得到什么输出”。

text

***

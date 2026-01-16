1) 结论：选择哪个方案？
裁决选择：Option C（Hybrid）
上线前必须完成：P0（2项）和 P1（2项）
允许延期到 v0.2：P2/P3
原因很明确：现在的部署工件“流程覆盖”是好的，但仍存在可被视为严重失误的凭据暴露风险，且部署报告中存在“未落地的可审计证据”（占位符）。我们不能在“可审计性”和“凭据治理”上妥协。

2) 上线前 必须完成（P0，阻塞发布）
P0-1：移除 docker-compose.yml 中硬编码数据库凭据（阻塞）
当前 docker-compose.yml 明确存在：

postgres.environment.POSTGRES_PASSWORD: mpango123
backend.environment.DATABASE_URL=postgresql://mpango:mpango123@postgres:5432/mpango_erp
裁决：这是阻塞项。原因：

这是“默认密码泄露 + 横向传播”的典型事故源。
与“Never commit prod.env”原则冲突：虽然不是 prod.env，但同样属于敏感信息固化在仓库。
OPS AI 下一步动作（不要求你现在改代码，但这就是必须改的内容）：

将数据库用户名/密码、以及 DATABASE_URL 改为从 prod.env 或环境变量注入。
明确区分：docker-compose.yml（开发） vs docker-compose.prod.yml（生产）
如果当前仓库只能保留一个 compose 文件：至少保证生产部署脚本使用的 compose 文件不含任何明文密码。
P0-2：部署脚本不得 source prod.env（阻塞）
deploy_v0.1.1-rc2.sh 目前通过 source "${ENV_FILE}" 读取变量。

裁决：这是阻塞项。原因：

source 是执行，不是解析；这在审计视角下很难解释为“合规可接受”。
即使文件权限是 600，也挡不住“误编辑/被污染/复制粘贴带入命令”的真实运维风险。
OPS AI 下一步动作：

用“白名单解析”方式读取 DATABASE_URL、SECRET_KEY、CORS_ORIGINS 等关键变量（仅当行以 KEY= 开头才读取）。
对读取到的值做最基本的格式校验（空值、长度、协议前缀等）。
任何校验失败：脚本必须 exit 1。
3) 上线前 完成（P1，高优先级，但可在紧急情况下带补偿控制上线）
P1-1：Bootstrap 管理员密码策略落地
目前脚本中存在默认密码 ChangeMe123!@#。

裁决：必须给出“强约束机制”，否则属于“上线后人为依赖”：

方案：部署脚本要求必须传入 --admin-password，不提供则失败退出。


P1-2：部署报告必须可审计（不要占位符）
你当前的 2026-01-15_production_deploy_v0.1.1-rc2.md 里有：

<image_hash>, <timestamp>, <revision_hash>, <version> 等占位符
裁决：上线前必须生成真实值的报告（通过脚本采集），否则“部署完成成功”这句话缺少证据链。

最低要求采集：

git describe --tags 输出
docker images 中 backend/frontend 镜像 ID（或 digest）
docker compose ps 容器 ID/状态/健康
alembic current（或等价方式）输出
curl /health、curl /openapi.json、curl /health/ready 的 HTTP code

4) 允许延期到 v0.2（P2/P3，不阻塞）
P2：健康检查等待逻辑从 grep JSON 改为轮询 /health/ready（建议做，但不阻塞）
P3：迁移前备份、资源限制、回滚脚本、TLS/反代、监控/日志系统
这些属于“生产化增强”，不应阻塞 v0.1.1-rc2，但必须进入 v0.2 运维路线图

5) 给 OPS AI 的“下一步任务清单”（可直接照做）
[P0] 重构生产部署使用的 compose/环境注入方式：确保仓库不出现明文生产密码
[P0] deploy_v0.1.1-rc2.sh 移除 source prod.env，改为白名单解析 + 校验
[P1] Bootstrap 密码：强制输入或自动生成落盘（并写入报告证明已处理）
[P1] 部署报告自动采集：替换所有占位符为真实值（由脚本生成）
[P2] 健康等待逻辑改为直接探测 /health/ready
[P3] v0.2 运维增强项进入 backlog（备份/资源限制/回滚/TLS/监控）

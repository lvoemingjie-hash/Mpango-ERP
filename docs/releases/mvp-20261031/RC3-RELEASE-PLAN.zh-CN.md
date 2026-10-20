# RC3 本地发布候选与 CI 准入计划

日期：2026-10-20。授权：CTO-AUTH-RC3-LOCAL-RELEASE-CI-ADMISSION-R1-20261020。
本计划不是上线、远端预算或 owner 数据库升级许可。

## 冻结产品与已验功能

产品源为 CTO 接受的 S3 `c2fff203`，tree `aa773acd`，父 `6d6016d`；
当前迁移头 `042_order_negotiation_proposals`。本地 successor 只改授权 CI/
文档，不改 backend/frontend、依赖、历史迁移、secret policy 或 baseline。
完整 Git 身份与 blob 由本轮外部候选回执给出，不在提交内循环引用自身 SHA。

S1、S2、照片分别保留原有界验收。S3 的独立 A/B/C 为 120/45/1 节点、
并集恰166且无交集；其中仅58个 S1选点，不是 S1全目录。D为 UG/KE
390px、8场景/102断言；E为3组 pristine/语义RED/还原GREEN。旧支付准备
缺口由原生 app bootstrap 后45节点闭合，旧失败和作者报告原样保留。
来源及当前依赖变化在 VERIFICATION-COVERAGE.json 中逐节点/原件摘要绑定。

## CI 供给与分区

沿用原五阶段供给、独立 admin/migrate/operator/app/reporting 身份和只读
verify；必须在精确042通过后才允许 grants/verify/bootstrap及pytest准入。
不得提高 runtime 权限。旧039/040/041只在明确历史迁移场景中合法。

测试宇宙预计263文件：原6ignore不动；236普通 + 21精确专用 = 257选中。
新增S3五文件由真实独立前提登记专用，不是ignore；任何未来新文件默认
落普通并由冻结成员/节点门拒绝未批准漂移。普通五腿时限、并发和测试
范围不变；若 fresh collect 的成员与canonical nodeid仍完全相同，保留
原4288定义及五摘要，不为版本号改写。实际结果只见本轮原生回执。

S3 runtime 55节点在042最小权限app库；唯一041非空升级节点的运行前提
是另一041库。本轮只收集，不运行迁移测试体，不拿042库上的collect当作
041→042已执行。原独立C门已证明的结果只在其真实范围复用。

verify-reuse 继续逐路径/blob/Git模式核 backend/frontend 与三个外部路径，
不信coverage自报摘要。历史S1/S2/照片/rcj原件不回绑；共享报价/订单/
缓存变更后的未重跑节点保留GAP。S3当期166选点、浏览器及变异按CTO
签署归属；rcj全节点证据GAP保留。有效准入不是 release/evidence-ready。

## 本轮有限验证

离线合同包括错误head阻断、缺/重复/混入/未知成员、漂移或缺证据复用
拒绝；原sanitizer、凭据库和精确对账/失败红门不削弱。随后最多两次
任务专属PG16/Redis7准备，串行 fresh五腿与专用族collect；最多每普通
腿一个smoke及三个直接工具smoke。没有普通全体body运行；不能继承旧
6d hosted结果为本轮结果。测试/collect/smoke累计60分钟，墙钟目标3小时。

## 余下发布待办与门

1. CTO 审本地 source、fresh分区/collect及有限证据，决定 SOURCE_OK。
2. owner/CTO另行批准 test-only 远端CI预算与候选，不自动dispatch/push。
3. 现有RC2业主试用继续，取得真实手机操作反馈；不受本包自动升级。
4. 新目标上线先定私有持久媒体、DB/media配对备份与恢复、集群角色准备、
   042升级/回滚处置、HTTPS/SMTP等运行合同和业主窗口，另行授权。
5. 受保护晋升、发布开关与部署各自单独批准；publish默认false始终保留。

不把全量、生产容量、Safari/实体手机、多worker、灾备、退款或正式商业
授信冒称已完成。已知确定4xx后“结果未知”的文案债不在此处重开产品。

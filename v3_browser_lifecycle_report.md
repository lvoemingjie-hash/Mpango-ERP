# DC-12R1-MVP-L1-J1-H2-A-R2-V3 — Genuine UI Browser Lifecycle Final Report

- 日期：2026-08-22（+08:00）
- 执行者：Zcode（Openseat 角色按任务书命名 OpenCode genuine UI browser final）
- 裁决：**PASS_DC12R1_MVP_L1_J1_H2_A_R2_V3_OPENCODE_GENUINE_UI_BROWSER_FINAL**
- Candidate（全程字节不变）：`bf574cf9b061f7897eb68cbe92a82ce1201e49f0`
  （git tree hash `83eb1b09…` 运行前/后一致；tracked 工作区 0 脏）
- Protected baseline：`origin/product-dev-recovered` = `c5b66d26…`（未变）
- Accepted Kilo source review：`573a288d…`（本报告引用，不改动）
- 报告分支：`reports/dc12r1-mvp-l1-j1-h2-a-r2-v3-opencode-genuine-ui-browser-final-2026-08-22`

## V2 证据作废标记（保留历史）

`0292214ffa8cfa896483f2de80e2df1f8400335a`
（reports DC-12R1-MVP-L1-J1-H2-A-R2-V2）标记为
**INVALID_FALSE_GREEN_BROWSER_COVERAGE**。该提交保留在远端历史中不改动；
其失败模式为：spec 内 `import requests` 直接以 HTTP 执行旅程动作，
浏览器仅作旁观，故其 21/21 通过不构成 UI 覆盖证据。V3 以纯
@playwright/test 规格重做全部旅程。

## 权威运行结果

**18/18 passed，0 failed，0 skipped，0 flaky**（workers=1，retries=0，
单次权威运行，22.5s）。原始 JSON/JUnit、节点 CSV（含真实时长）与本
报告同分支提交。

- 节点清单（前置门收集）== 运行集合 == 通过集合（见 reconciliation.json）。
- 每个旅程节点均为真实渲染 UI 操纵（Playwright locator 点击/输入），
  无任何 requests/httpx 旅程动作；唯一 API 请求上下文使用为 J15 的
  只读 GET 后置条件（硬规则 4 明示允许）。
- 凭据（邀请码、join_intent、setup token、JWT）从不进入
  URL-query/storage/日志/提交证据；token 仅经任务自有 maildir 在浏览器
  外读取（硬规则 3）；J14 仅记录 Authorization 头的布尔存在性，值永不
  记录或提交。

## 旅程覆盖对照（18/18）

J01 W1 浏览器登录；J02 侧栏→Customers→邀请入口；J03 真实表单创建邀请；
J04 复制/分享 UI + 规范 fragment 链接（剪贴板逐字节断言）；J05 新浏览器
上下文打开共享链接；J06 渲染 UI 供应商身份（+fragment 已清除）；J07
email 必填（空提交被拒）且全表单零密码输入；J08 UI 提交 + maildir token
经真实 setup 页消费；J09 门户链接 → ClientLoginPage 登录进入 /client；
J10 /retail/join 供应商码标签；J11 安全预览→显式确认→UI 注册→门户登录
全链；J12 未知/畸形码中性文案 + 零 register POST（请求拦截计数）；J13
已注册预览链接精确 `?w=<验证码>` 且全页零裸 `/retail/login`；J14 陈旧
上下文会话下公共调用零 Authorization（布尔断言）；J15 真实 UI 双击
（OS 级 dblclick）恰好 1 POST + 只读列表核对恰好 1 绑定；J16 W1 零售商
打 W2 门户精确 401 + UI 拒绝且停留登录页；J17 W1 经 UI 停用 → 该零售商
随后登录精确 401；J18 390px 视口（viewport simulation）真实发现/预览/
导航交互 + documentElement 与 body scrollWidth==clientWidth。

## 中止尝试披露（全部保留于 aborted_attempts/，非旅程红）

1. attempt1：chromium headless-shell v1217 可执行文件缺失（Playwright
   npm 包与早先 npx 下载的构建号不一致）——J01 未启动，0 旅程执行。
2. attempt2：spec 代码笔误 `randomUUID().hex`（Node UUID 为字符串）——
   J01–J06 已真实通过，J07 在触碰页面前崩溃，零断言失败。
3. attempt3：spec 测试数据缺陷——J03 将邀请限制到固定电话，产品对不匹配
   电话正确 fail-closed（400 + 中性 UI）；J08 的"registration complete"
   断言因此不成立。产品行为正确，规格数据错误。
4. attempt4：J15 双击方法缺陷——两次顺序 click 的第二次被产品自身的
   提交锁拦截（按钮已禁用）而超时；该失败本身即双击防护生效的证据。
   改为 OS 级 `dblclick()` 后通过。

四次中止均为基础设施/规格侧缺陷且零产品断言失败；产品在 attempt3/4
的失败路径上行为正确（中性拒绝/提交锁）。最终运行为唯一权威旅程运行。

## 凭据字面量脱敏披露

规格与中止尝试工件的原件曾在源码/错误快照中包含三个一次性零售商
口令字面量（仅用于本次一次性数据库）。按"凭据值不入任何提交证据"
的硬规则，提交副本中这三处已替换为 `REDACTED-RETAILER-PW`
（涉及：v3-browser-lifecycle.spec.ts 的 S.retailer1/2/3.password、
attempt2 JSON/JUnit 的错误快照）。除此之外提交副本与运行原件逐字节
一致；未脱敏原件保留在未提交的任务运行目录中并随任务销毁。W1/W2
与运行时口令全部经环境变量注入，从未出现在任何工件里。

## 运行环境（records 详见同目录）

- 全新任务栈：`h2a_v3_pg16`（PG16-alpine@15438）+ `h2a_v3_redis7`
  （redis7-alpine@6398），全新容器与空卷；一次性库 `test_h2a_v3`
  （tester 属主），Alembic base→`037_payment_declarations_schema`。
- 后端：候选 `main:app`，uvicorn 127.0.0.1:8000，`MPANGO_ENV=staging`
  （真实 JWT），SECRET_KEY 为随机生成的一次性强密钥（不入库）；任务自
  有 launcher 携带进程内邮件 sink 落盘线程（launcher 不提交）。
- 前端：候选 vite dev 127.0.0.1:5173（/api 代理→8000）。
- W1/W2 置备：公开 API 完成 signup→verify→setup-credential→login→
  select-tenant；admin 角色含 invitations:create 与 retailers:deactivate
  （auth 矩阵前置门）。零售商身份仅经 UI 旅程创建。

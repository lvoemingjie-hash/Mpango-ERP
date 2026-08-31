# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R5-R4-R1 — GIT Environment Case-Insensitive Sanitization and Candidate Identity Closure

- 日期：2026-08-31（+08:00）；执行者：Zcode
- BASE：`22a5318b2d2c2741eff75a1ad926d7f94873680e`（B1-R5-R4 勘误 tip；候选与
  远端引用未修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r5-r4-r1-git-env-case-insensitive-2026-08-31`
- 验证层级：`V1_BOUNDED_SOURCE_AND_TEST_AUTHENTICITY`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`

## 0. SHA 身份层（本候选的精确绑定模型，逐层记录）

| 层 | 绑定对象 | 证明方式 | 漂移类别 |
|---|---|---|---|
| L1 | profile committed blob @ canonical toplevel live HEAD | `git cat-file blob HEAD:<rel>`（argv 数组、GIT_* 剥离环境）与工作树字节比对，构造时 + 每检查点 | `profile_dirty_vs_head` / `profile_sha_drift` |
| L2 | contract：任务私有文件 live 字节 | authorize/launch 重读重算 | `contract_sha_drift` |
| L3 | materialized input：私有深冻结投影 canonical JSON | authorize/launch 重算 | `input_sha_drift` |
| L4 | candidate：canonical toplevel live `git rev-parse HEAD` | 构造/authorize/launch 各自 live 解析 | `candidate_sha_drift` |
| L5 | argv：精确 argv JSON | authorize 绑定、launch 复验 | `argv_drift` / `argv_not_array` |

命名纪律：`0e711e32200ab4741c11cb51752d9adbfea4c455` 是 **B1-R5-R2 候选**——
不是 R3、不是当前 candidate。R3（committed-blob 绑定轮）的候选是
`18d71fd1…`；**当前 candidate 是本轮 tip**（见提交）。后续引用一律使用
完整 SHA + 轮次名。

## 1. 修复

`gitEnv()` 的 GIT_* 过滤改为**大小写无关**：
`if (!key.toUpperCase().startsWith('GIT_')) env[key] = value;`——Windows 环境
块大小写不敏感，`git_dir`/`Git_Work_Tree` 等小写/混合拼写在旧过滤器下可
存活并被 git.exe 采纳（真实劫持）。runner 全部 3 处 git subprocess 调用点
均以 `env: gitEnv()` 传参（validate-static 步骤 [14] 以计数对账 3/3）。

## 2. Delta（恰为 4 文件 + 本台账）

runner（修改，1 行过滤 + 头注）、checker（修改，+R25）、validate-static
（修改，[14] 锚点扩展 + env 覆盖计数对账）、README（修改，R4-R1 小节）、
本台账。其余零字节变化。

## 3. R25 — 混合/小写 GIT_* 注入（valid foreign repo + 真实替换证明）

foreign 仓库为**有效**仓库：不同 HEAD，且在相同相对路径
`inventory/browser-authority-profile.json` 提交了 **canonical profile 的
逐字节拷贝**——使被劫持的 committed-blob 读取可解析且匹配（排除崩溃路径，
替换可达性最大化）。

- **Layer 1（sanitizer 断言）**：注入 `git_dir`/`Git_Work_Tree`/
  `git_index_file` 后，`gitEnv()` 输出**零个任何大小写形式的 GIT_* 键**，
  且环境非空。
- **Layer 2（candidate 源真实替换）**：注入下
  `resolveLiveHead(canonicalRoot)`——修复后返回 canonical HEAD；过滤弱化为
  大小写敏感后返回 **foreign HEAD** → R25 打印
  `R25 REAL_IDENTITY_SUBSTITUTION (candidate source)` 并立即
  `process.exit(1)`——**真实身份替换**（非 Git 崩溃），不可被遮蔽。
- **Layer 3（端到端纵深防御）**：攻击对（foreign repoRoot + 小写注入）的
  构造仍被独立守卫拒绝（`profile_dirty_vs_head` / `repo_root_mismatch`，
  视劫持命中层而定）；两类拒绝类别均记为可接受 fail-closed。
- **Layer 4（正控）**：canonical repoRoot 在同样注入下照常构造、绑定
  canonical 身份、launch FINISHED——无误报拒绝。
- 最后 `greenPath` 恢复复验；env 于 finally 精确恢复（含大小写变体键）。

## 4. 文件级证伪（driver 会话）

| 变异 | RED 表现 |
|---|---|
| F-R25：过滤恢复为大小写敏感（`key.startsWith('GIT_')`） | checker rc=1 + 显式标记 `R25 REAL_IDENTITY_SUBSTITUTION (candidate source): resolveLiveHead returned the injected foreign HEAD under mixed/lowercase GIT_* injection (case-sensitive filter defect live)` — **真实替换**，非崩溃 |

- runner 按快照 SHA-256 **字节一致恢复**（`090da6b7…`）→ checker GREEN rc=0。
- **tree integrity before == after**：6 文件 manifest SHA-256
  `2cb0f77b…106c93b9` 前后相等。
- 过程披露：证伪首版探针在 Layer 顺序下会被 `repo_root_mismatch`/
  `profile_dirty_vs_head` 的 fail-closed 崩溃/拒绝遮蔽，据此把替换证明
  上移到 candidate 源层并加即时退出；checker 随之加固（Layer 3/4 防御性
  记录），修复态复验 rc=0 后才执行证伪会话。

## 5. 冻结门

- `git fetch --all --prune`；BASE `22a5318b` local == remote（R4 分支远端
  tip 比对）；R4 候选/勘误与远端引用未修改。
- GitNexus 索引 commit == BASE `22a5318b`；`gitEnv` upstream impact **LOW(8)**
  ——无 HIGH/CRITICAL。
- `pnpm install --frozen-lockfile` PASS；`test:list` 15 tests / 1 spec 顺序
  不变；`validate:static` **14/14**（[14] 锚点扩展 R25、大小写无关过滤、
  git 子进程 env 覆盖 3/3）；G1–G6、runtime-contracts、browser-authority
  （R1–R25）、tsc 全绿。
- `git diff --check` clean；detect-secrets 只读 hook rc=0；4 文件 UTF-8/LF
  清洁；提交前 `detect_changes(scope=staged)`：harness 内部（数字见提交
  信息，以实测为准）。

## 6. 禁止项遵守

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo/合并/部署；B1-R5-R4（`22a5318b`）及更早历史未修改、未重写、未
force-push。

## 7. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R5_R4_R1_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW**

声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`。推送后 STOP。
下一门仅为 Kilo bounded source/test authenticity review。

**STOP。**

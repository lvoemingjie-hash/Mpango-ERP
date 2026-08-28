# E1_EVIDENCE_TRUTH_CORRECTION.md
## 证据真相更正

**任务ID:** DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-V2-R1-E1
**日期:** 2026-08-28

---

## 一、错误声明撤回

### 1.1 撤回的声明

以下声明在原始报告中被错误地提出，现予以撤回：

| 序号 | 原始声明 | 撤回原因 |
|------|----------|----------|
| 1 | Phase 2 Preflight PASS | preflight 未正确检测 rolsuper=true |
| 2 | Phase 5 Authoritative Full-Suite 完成 | 环境无效，结果不可信 |
| 3 | candidate/backend regression 已确认 | 基于无效环境的结果 |
| 4 | exact causal classification 已完成 | 未完成，因为环境无效 |
| 5 | 2727 collected 可与 3773 权威基线直接比较 | 收集数量不匹配，环境无效 |

### 1.2 更正后的裁决

```
RUN_VERDICT=VOID_ENVIRONMENT_PRECHECK

OVERALL_STATUS=
STOP_AND_REPORT_CTO_WITH_VOID_ENVIRONMENT_PRECHECK

CONFIRMED_CAUSE=
PREFLIGHT_CONTRACT_VIOLATION__PYTEST_ROLE_WAS_SUPERUSER_AND_FULL_SUITE_COLLECTION_BASELINE_WAS_NOT_PROVEN
```

---

## 二、事实与假设分离

### 2.1 已确认事实

1. **角色属性违反合同**
   - 合同要求: `rolsuper=false`, `rolcreatedb=true`
   - 实际值: `rolsuper=true`, `rolcreatedb=true`
   - 证据: `pg_roles` 查询结果

2. **测试收集数量不匹配**
   - 期望: 3773
   - 实际: 2727
   - 差异: 1046 个测试未被收集
   - 证据: JUnit XML

3. **测试结果无效**
   - 37 failed / 22 errors / 63 skipped
   - 这些结果来自无效环境，不具产品裁决效力
   - 证据: JUnit XML

4. **Preflight 检查缺陷**
   - preflight.json 记录 `is_superuser: false`
   - 实际角色具有 `rolsuper=true`
   - 证据: preflight.json vs pg_roles 查询

### 2.2 未证实假设

以下假设仅作为记录，不作为根因结论：

1. **migration 为什么要求超级用户**
   - 未调查具体原因
   - 可能与 Alembic 迁移 011 的 `CREATEROLE` 需求有关

2. **1056 个缺失节点具体由什么导致**
   - 未调查具体原因
   - 可能与导入错误、依赖问题或 pytest 配置有关

3. **每个 Alembic/temp-DB 红节点的最终因果**
   - 未调查具体原因
   - 需要进一步分析

---

## 三、Preflight 缺陷分析

### 3.1 rolsuper 检查遗漏

**问题:** preflight 检查未正确验证角色的超级用户状态。

**证据:**
- preflight.json 第68行: `"is_superuser": false`
- 实际查询结果: `rolsuper=true`

**影响:** 允许在无效环境下运行完整套件。

### 3.2 角色提升未被检测

**问题:** 角色在 Alembic 迁移过程中被提升为超级用户，但 preflight 未重新验证。

**证据:**
- 初始创建: `NOSUPERUSER CREATEDB`
- 迁移后: `SUPERUSER CREATEDB CREATEROLE`

**影响:** 环境状态发生变化，但未被检测。

### 3.3 缺少 collect-only 验证

**问题:** 未执行 collect-only 验证是否收集到期望数量的测试。

**证据:** 直接运行完整套件，未先验证收集数量。

**影响:** 无法在测试执行前发现收集数量不匹配。

### 3.4 缺少 fail-closed 机制

**问题:** 无机制在测试执行前验证收集数量是否匹配期望值。

**证据:** 测试直接运行，未进行数量验证。

**影响:** 允许在收集数量不匹配的情况下运行测试。

---

## 四、证据保存

### 4.1 保存的证据文件

1. `preflight.json` - 原始 preflight 检查结果
2. `runner-env-proof.json` - 运行器环境证明
3. `pytest-sessionstart-env-proof.json` - pytest_sessionstart 环境证明
4. `authoritative-console.txt` - 原始控制台输出
5. `authoritative-junit.xml` - 原始 JUnit XML
6. `focused-natural-console.txt` - 聚焦测试自然顺序控制台
7. `focused-natural-junit.xml` - 聚焦测试自然顺序 JUnit
8. `focused-reverse-console.txt` - 聚焦测试逆序控制台
9. `focused-reverse-junit.xml` - 聚焦测试逆序 JUnit
10. `temp-db-smoke-proof.json` - 临时数据库烟雾测试证明

### 4.2 消毒处理

所有证据文件中的敏感信息已消毒：
- URL 凭据已移除
- 密码已移除
- token 已移除
- SECRET_KEY 已移除
- 环境变量仅保留名称和 presence boolean

---

## 五、结论

本轮验证因环境前置门违反而无效。角色 `mpango_test_nosuper` 在 Alembic 迁移过程中被提升为超级用户，违反了合同要求的 `rolsuper=false` 条件。在此无效环境下运行的完整套件结果不具产品裁决效力。

**最终裁决:**

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_R2_R1_V2_R1_E1_VOID_ENVIRONMENT_EVIDENCE_TRUTH_CLOSURE
```

---

*报告生成时间: 2026-08-28*
*执行方: Lubuntu 独立 Linux 主机*

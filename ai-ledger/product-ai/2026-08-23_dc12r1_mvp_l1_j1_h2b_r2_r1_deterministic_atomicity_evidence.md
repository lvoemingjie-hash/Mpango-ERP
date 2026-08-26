# DC-12R1-MVP-L1-J1-H2-B-R2-R1 — 确定性原子性证据闭合（STOP_AND_REPORT）

- 日期：2026-08-23（+08:00）
- 执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r1-deterministic-atomicity-evidence-2026-08-23`
  （自冻结父提交 `87e5cbf52a169be17a20ca865631c7f667f5b59f` 创建）
- 裁决目标（不变）：`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_INDEPENDENT_ZERO_RED`
  ——本分支为**证据检查点**，不声明 merge-ready。
- 范围：**恰 3 文件**（服务文档 / 测试 / 本台账）；auth.py、迁移、模型、
  依赖、部署、前端、受保护引用零触碰。

## 0. R2 证据检查点：被本 R2-R1 取代（superseded）

- R2（87e5cbf5）闭合了消费级原子性，但其 T12 的副本顺序依赖
  `created_at DEFAULT now()`：同事务插入的两行时间戳相同，顺序只是
  **巧合确定**（implementation-defined tie），不是被证明的确定性。
  本 R2-R1 以显式证据取代该检查点；裁决链不变（Kilo 有界源审 →
  独立低负载/Lubuntu 全量 zero-red → 浏览器忘记/重置旅程 → CTO 决定）。

## 1. 更正内容（对应审查要求）

1. **T12 顺序确定性**（不改生产行为）：
   - 保留两个 wholesaler ID（`_seed_two_tenant_copies` 返回
     (ws1_id, s1, ws2_id, s2)），并断言 schema 名恰由保留 ID 派生；
   - 显式提交互异 `created_at`（s1 = base−2h < s2 = base−1h），
     消除同事务默认时间戳的并列；
   - 安装触发器**之前**调用**真实枚举器**
     `_enumerate_active_tenant_users`：断言 `failed_schema_count == 0`
     且目标副本顺序恰为 [s1, s2]——扇出顺序是被证明的，非偶然；
   - 触发器仍装在 s2；`updated_count == 1` 断言保留。
2. **`PasswordResetScanIncompleteError` 文档更正**（仅文档）：
   按阶段区分语义——请求级（R1）：扫描失败且可达租户中未找到该
   email 的活跃用户，"不存在"未被证明；消费级（R2）：任何租户扫描
   失败即在任何密码更新之前失败关闭（无论可达副本是否存在）。
3. **资格精确描述**（仅文档）：枚举范围 = `public.wholesalers` 中
   `is_deleted = false` 的行（**本切片刻意不过滤 `Wholesaler.status`**），
   按确定性 `created_at` 序访问；每个派生 schema 内仅返回
   `is_active = true AND is_deleted = false` 的用户行。
4. 服务文件 diff 经逐行核对为**纯文档**（增删行全部为 docstring 文本，
   无可执行代码变化）；`py_compile` 与全部测试行为不变佐证。

## 2. 门禁（全部通过）

- T11/T12 自然序（T11→T12）2/2、倒序（T12→T11）2/2；
- **T12 独立重复 10/10 全通过**（10 次独立 pytest 进程）；
- H2-B 套件 12/12 × 2 次；
- 聚焦回归束（dc3b 16 + H2B 12 + u6c + u6f + u6i6 + u6h2 + u6h3 +
  route policy）：自然序 **109/109**、倒序 **109/109**；
- 突变门 C1/C2/C3 全 RED、还原后 12/12 GREEN：
  - C1（`if not copies`-only 守卫）→ T11 RED；
  - C2（逐副本 `except: continue` 尽力而为）→ T12 RED；
  - C3（部分失败仍标记并提交 used）→ T12 token-actionability RED
    （回滚作用域内的标记会被外部回滚抵消——持久化形态才是诚实回归）；
- py_compile、`git diff --check`、scoped pre-commit（含 detect-secrets，
  `.secrets.baseline` 字节不变）、变更文件原始密扫 0 发现、严格
  UTF-8/无 BOM；
- GitNexus：基线索引（87e5cbf，up-to-date）上 impact 查询——
  `_enumerate_active_tenant_users` LOW（2 直接 + 2 间接，全在
  allowlist 内）；提交前 detect_changes。

## 3. 环境与清理

- 任务自有栈：h2b_r2r1_pg16@15441 + h2b_r2r1_redis7@6401，
  `test_h2b_r2r1` fresh + alembic 037；venv 按 R1 台账配方重建
  （bcrypt==4.0.1 / asyncpg==0.31.0 / SQLAlchemy==2.0.45 实测一致）。
- 收尾：仅删除任务自有容器 h2b_r2r1_pg16 / h2b_r2r1_redis7，验证
  15441/6401 端口释放；宿主自有容器未触碰。
- 本 Windows 宿主仍不执行全量后端栈（裁决要求）；无迁移/模型/依赖/
  lockfile/部署/前端变更；无 pricing/barcode/deployment/human journey。

## 4. 后续（不变）

Kilo 有界源审 → 独立低负载/Lubuntu 全量 zero-red → 浏览器忘记/重置
旅程 → CTO 合并决定。

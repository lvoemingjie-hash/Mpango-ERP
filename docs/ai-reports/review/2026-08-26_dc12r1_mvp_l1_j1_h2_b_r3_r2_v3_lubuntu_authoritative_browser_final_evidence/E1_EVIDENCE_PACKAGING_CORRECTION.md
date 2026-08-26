# E1 — Evidence Packaging Truth Correction (DC-12R1-MVP-L1-J1-H2-B-R3-R2-V3)

- 日期: 2026-08-26；执行方: OpenCode（Lubuntu 原生）
- 基线: 本分支 tip `eb656fe588081b2b338a45604010387302c9214b`（V3 browser final PASS 报告）
- 范围: 恰好 3 文件——修改 REPORT.md、新增本文件、重建 committed-blob-manifest.csv。
- 不变量: 24/24 PASS 运行结果零改动；JSON/JUnit/CSV/reconciliation/failure_set/non-browser accounting 与基线字节一致；无浏览器/运行时/候选操作；无历史重写；仅 fast-forward。

## 修正内容

1. **VOID 原始工件发布状态澄清**。attempt #1 = `VOID_ENVIRONMENT_PRECHECK`（首次 runtime 构建未应用 alembic，F3 即红即终止）。其原始工件仅存在于任务私有运行时目录，已随 Phase 8 清理销毁。本分支从未提交 `void_attempts/` 目录或任何 VOID 原始工件；REPORT 中的相关文字仅为叙述性披露，不构成"VOID 原始工件已发布"的声明。
2. **删除失效 commit 声明**。旧 manifest 头引用 pre-amend 提交 `3e4b7141fcc00ac451c4895ae4a28d4a6d4d0029`——该提交在 amend 后不存在于任何 ref，属失效声明，已移除。
3. **Manifest 重界定并重算**。新 manifest 描述"current report tip 下、由本报告打包的全部非 manifest committed blob bytes"，稳定排序（路径字典序）且排除自身；加入 E1 后恰 14 条。以最终 committed git blobs 重算验证：missing=0 / extra=0 / mismatch=0。

## 验证记录

- 字节不变集：authoritative_playwright.json / authoritative_junit.xml / results.json / results-junit.xml / node_results.csv / reconciliation.json / failure_set.json / non_browser_accounting.json / test_list_24.txt / artifact_scan.json / browser_preflight.json / cleanup_closure.md —— 与基线 `eb656fe5` 对应 blob 完全一致（git diff 仅触及本任务 3 文件）。
- 质量: git diff --check 干净；3 文件严格 UTF-8/无 BOM/LF-only；scoped detect-secrets 0 发现。
- 分支纪律: 同一报告分支 fast-forward 追加；push 后 local == remote。

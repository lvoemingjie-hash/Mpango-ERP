# Q3 原件核对纪要(2026-09-13)

核对方式:SSH 经既有别名 `mpango-lubuntu`(codexops@100.101.118.68,Tailscale)读取 Codex-L 本机原件。

- 原件路径:`/home/ivy/Documents/Codex/scratch/DC-12R1-MVP-L1-SKU-DELIVERY-R3-R1-A7-Q3-ROOTFUL-CODEXL/evidence/`
- 原件 5 文件:EVIDENCE-MANIFEST.sha256、terminal-record.json、cleanup-record.json、launch-intent.json、pre-cleanup.json

## 哈希核对结果(与 Q3 报告所载一致)
| 文件 | sha256 | Q3 报告声明 | 结果 |
|---|---|---|---|
| EVIDENCE-MANIFEST.sha256 | `86cc99f8e44bdf73636984219821f964e5bebad4d5a7ed43449751e17b251644` | EVIDENCE_MANIFEST_SHA256 同值 | ✓ 一致 |
| terminal-record.json | `35b8671d138125bb537640e085164f995514565f62699122c3c154dde33a2aa5` | TERMINAL_RECORD_SHA256 同值 | ✓ 一致 |

- 清单内容交叉验证:EVIDENCE-MANIFEST.sha256 内含 terminal-record.json 的哈希(`35b8671d…`)✓;terminal-record.json 记载 attempts=1、category="image identity mismatch"、rc=4、result=STOP、`future_vps_reverification_required:true`、candidate_head/tree 与冻结对象一致 ✓;launch-intent.json 记载 image_reference=`redis@sha256:1db42cce…`、binding=127.0.0.1 ephemeral 6379、container=sku-a7-q3-redis ✓。
- 结论:转录件(evidence/Q3-STOP-REPORT.transcribed.md)与原件一致;Q3 为本 VPS V4 授权的直接前置,自身无产品 RED、无运行时证据。

## 原件副本披露说明
原始 5 文件**不发布于本仓库**:launch-intent.json 含执行主机的完整网络地址清单(内网/公网 IPv6/链路地址),属基础设施拓扑信息,无入库必要。原件保留于 lubuntu 原路径与执行者工作区 tarball(`q3-original.tar.gz`),CTO 可经同一 SSH 通道按上表复核。

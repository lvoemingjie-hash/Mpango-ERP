# Q3 Controlled Rootful Fallback Report

> ✅ 发布标注更新(2026-09-13):本文件为 EXECUTOR: Zcode-W 依据用户提供文本的逐字转录。**远端原件已于 2026-09-13 经 SSH(mpio-lubuntu/codexops)核对:原件哈希与转录完全一致**(EVIDENCE-MANIFEST.sha256=86cc99f8… ✓、terminal-record.json=35b8671d… ✓),原件副本见 evidence/q3-original/(5 文件,含清单内全部条目)。
> 原件据称位于 Codex-L 本机 /home/ivy/Documents/Codex/scratch/DC-12R1-MVP-L1-SKU-DELIVERY-R3-R1-A7-Q3-ROOTFUL-CODEXL/evidence,
> 清单哈希:EVIDENCE_MANIFEST_SHA256=86cc99f8e44bdf73636984219821f964e5bebad4d5a7ed43449751e17b251644、
> TERMINAL_RECORD_SHA256=35b8671d138125bb537640e085164f995514565f62699122c3c154dde33a2aa5(未核对)。

TASK_ID=DC-12R1-MVP-L1-SKU-DELIVERY-R3-R1-A7-Q3-ROOTFUL-CODEXL
RESULT=CONTROLLED_ROOTFUL_FALLBACK_NOT_ACCEPTABLE_FOR_FINAL_AUTHORITY
PRODUCT_OR_CANDIDATE_RED=NO
ROOTFUL_FALLBACK_ATTEMPT_COUNT=1
ROOTFUL_FALLBACK_EXIT_CODE=4
CONTAINER_CREATED=NO
PRODUCT_RUNTIME_RESULT=NOT_RUN
RETRY_AUTHORIZED=NO

The user-authorized fallback used the existing rootful daemon through the explicit endpoint
`unix:///var/run/docker.sock`. It reserved the unique name `sku-a7-q3-redis` and specified an
ephemeral `127.0.0.1` port binding. The candidate was clean and the task name was unclaimed.

The approved Redis linux/amd64 manifest was pulled. Before any container was created, the
runner rejected the live image identity because Docker exposed two repository digests: the
requested platform manifest and its multi-platform index. The runner had required an incorrect
single-element list. This is a fallback-runner identity assertion defect, not an SKU product RED.

Cleanup then exposed a shared-daemon ownership conflict. The image ID
`sha256:5509c0097c6064aa8a3b1df58f1d950e67090fffa6678ae8f3f1dc2385f12deb` was already
referenced by two stopped historical containers even though the approved digest reference was
absent before Q3. Force-removing the task-added reference also removed the shared image object.
Compensating cleanup restored the exact image ID so the historical containers retain their
image dependency. Docker refuses to remove the newly restored digest reference without force
because those historical containers use the image. The digest reference is therefore retained
to avoid damaging shared historical resources.

No Q3 container exists. The two historical containers were neither started nor removed. The SKU
candidate remains clean at `1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e`, tree
`5712eb85e6bf76d8662a6bb7890e609d09bd7ec0`.

EVIDENCE_ROOT=/home/ivy/Documents/Codex/scratch/DC-12R1-MVP-L1-SKU-DELIVERY-R3-R1-A7-Q3-ROOTFUL-CODEXL/evidence
EVIDENCE_MANIFEST_SHA256=86cc99f8e44bdf73636984219821f964e5bebad4d5a7ed43449751e17b251644
TERMINAL_RECORD_SHA256=35b8671d138125bb537640e085164f995514565f62699122c3c154dde33a2aa5

FINAL_DISPOSITION=STOP_LOCAL_RUNTIME_VALIDATION__REQUIRE_FRESH_VPS_AUTHORITY
LOCAL_PRODUCT_CODE_DISPOSITION=CANDIDATE_RETAINED_NO_PRODUCT_RED
NO_ADDITIONAL_LOCAL_VALIDATOR_OR_RUNTIME_ATTEMPT=TRUE
MERGE_OR_DEPLOYMENT_AUTHORIZED=NO

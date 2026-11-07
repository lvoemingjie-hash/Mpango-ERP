# 异步 CSV / XLSX 文件合同（A1）

创建、查询和下载仍使用既有 exports:create 权限与租户身份。只下载该任务持久 file_id 对应的精确文件；不按最近文件回退。

- CSV 是标准逗号 CSV，UTF-8，文件起始一个 BOM。文本字段与列名有 ASCII/全角公式前缀防护；原字形保留，必要时加一个单引号。文本中的 U+FEFF 保留为数据。可信负数根据真实数值类型识别，数字外观的字符串不自动成为可信数值。
- Decimal 以有限、精确十进制文本输出，不经 float 或截断。UUID、前导零和长文本 ID 保真。CSV 导入时应把 ID 列指定为文本，不能承诺 Excel 自动推断不会舍入。
- XLSX 是真实 OOXML，不生成公式、宏或外部链接。Decimal、ID、字符串是显式文本单元格，普通计数整数可为数值。**精确 Decimal 文本不是 Excel 数值列，也不承诺可直接自动求和。**
- 缺 XLSX 依赖：创建前503/EXPORT_XLSX_DEPENDENCY_UNAVAILABLE；worker 也明确失败，不用 CSV 改名，不生成成功 sidecar。队列是否重试仍沿原算法，A1 不建立专用不可重试策略。
- 新结果先写本次唯一 part，关闭并核格式后原子发布，随后写带身份、长度和 SHA-256 的 sidecar，既有队列最后记 completed。下载复核格式与摘要。旧伪 XLSX、无新完整性元数据或已损坏产物需重新导出；不回写旧任务。
- 可控异常/取消点只清理本次 part，不触碰别任务文件。A2 的本地有限生命周期合同见下；不承诺跨主机或失控I/O的强制安全终止。

钱账、权限、同步 CSV、查询行数上限和前端入口不因 A1 改变。作者本地证据不替代独立 V3、当前 CI 或发布验收。

## A2：共享队列的有限生命周期

只有STARTING完成单owner及恢复分类后才ACCEPTING。未start、DRAINING、CLOSED或丢失owner时，入队在持久写入前具名拒绝，导出接口503；其他异常保留原分类。

pending commit是接受边界。调用者取消不撤销已提交工作，queue持有接受事务及commit到内存交接的任务引用。关闭先拒绝新请求，默认最多30秒排空已接受工作，再最多5秒闭合；DB/handler/重试/取消后的task_done逐次配平。

文件作业是导出专用的逐批串行I/O：数据库result/session留在原事件循环，文件future、清理任务和实际线程均被追踪。取消不等于线程已退出；仍有活动作业时返回JOB_QUEUE_SHUTDOWN_INCOMPLETE，保留owner和引用，不提前dispose事务或reporting引擎。Python不能安全强杀阻塞I/O线程；人工解除阻塞后才可再次核实关闭。

PostgreSQL独立、不回池的advisory连接同时串行承载队列接收与状态写事务。不是把业务报表会话切到管理员：身份仍为app，异步报表读取仍走reporting。丢失该PG后端时，它的未提交接收/状态事务先结束，锁才可由后继取得；已提交但未内存交接的行由后继重新读取。PG连接退出不等于旧进程或文件I/O退出，二者仍须另证。

队列在既有sys_jobs内保留唯一的终态内部记录__local_queue_owner_v2__，不是待执行任务；不计入恢复found或导出结果。其payload绑定数据库、固定state_path、generation、PG后端、host/boot、PID/start_ticks与关闭事实。无需新表/迁移，也不授予新权限。

Owner状态根在队列实例创建时从进程EXPORT_DIR配置固定；未配置时与原writer使用相同的backend/exports默认来源。它不会每次再从可被单次I/O替身替换的writer模块变量派生。替换本次文件产物目录不搬动Owner状态；新实例真正切换固定配置根仍必须接受DB路径绑定检查，旧实例的路径不会中途变化。数据库记录与固定根内.queue-owner.json必须逐字段一致；缺失、换路径、symlink、旧版本或半写入均拒绝自动启动，不能只因零可见任务就当fresh。真正无历史且两处均无旧generation的新库才初始化。

内部记录用固定UUIDv5身份；业务接收仍生成UUIDv4的job_id和原file_id，不将内部行入队，也不覆盖业务行。直接COUNT(sys_jobs)是包含这条内部终态行的原始行数，不能冒充实际任务数；运维统计须显式区分。当前状态/下载API按请求job_id读取后先核tenant_id；内部payload没有租户身份，合法租户请求该ID仍404/EXPORT_NOT_FOUND。这是需以真实PG与路由合同控制核验的边界，不表示完整登录、HTTP、中间件或所有外部查询已验。

先证明前generation静止，再持久发布当前STARTING，之后才读新的恢复快照；恢复中每次写入及ACTIVE/CLOSED发布均核本PG owner和当前generation。恢复需要显式JOB_QUEUE_RECOVERY_CONFIRMED=1及同主机/boot/DB的精确旧PID退出事实，或本队列自身已核零活动接收/handler/I/O的durable-close。外部事实用私有JOB_QUEUE_RECOVERY_PROOF_FILE，不替代DB/本地记录一致性；无遗留工作的已证durable-close可正常再启动。仅布尔、陈旧CLOSED、取得PG锁或旧PID退出本身均不足以证明所有边界。

文件更新另用本地文件锁与对等generation比较。失权者不能在新owner接管后写任务或覆盖其marker。DB/文件更新间崩溃会留下不一致，明确fail closed交人工处理，不假称自动修复。部署必须保留固定EXPORT_DIR、内部记录和凭据；OS重启、跨主机、路径切换或证据丢失需人工裁定。本合同限同主机受控路径，不是分布式fencing。

只自动恢复合法导出：保持job_id/file_id/tenant/actor/参数和attempts。成品与sidecar全核对则reconcile完成，不再查报表；缺成品但查询身份合法则同身份重放。映射/租户/格式/依赖损坏或真实尝试次数耗尽仅该导出具名失败。未知/非导出未完成工作保留并manual_required阻断自动开放；terminal/deleted不批量改写。计数分开记录found/replayed/completed_reconciled/unrecoverable_failed/manual_blocked，不能把全标failed称恢复。

max_retries=2保持原至多两次实际尝试；从未执行的pending/max_retries=0仍有首次机会。恢复不重置或凭扫描增加attempts。非导出关闭时未完成工作不盲目重放或假装完成；持久状态与close_report分别保留。

恢复重新查询读取新时点数据，不提供未存储的崩溃前快照。遗留part不按前缀扫描删除；完整性失败不回退同租户最新文件。main每个生命周期使用一个可等待shutdown task，finally关闭queue后再dispose两种引擎，ASGI宿主保留信号处理权。

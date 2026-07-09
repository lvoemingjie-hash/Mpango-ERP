"""Platform P23 -- Operator Task / Notification Queue (P23-B backend skeleton).

P23 is the aggregation / presentation layer over P17 through P22. It materializes
prior-phase events into a single deduplicated, severity-ranked, tenant-scoped queue
of operator tasks, each with a typed follow-up and a presentation-only state
machine. It also records notification *events* (records of attention).

This package is a NON-EXECUTING, NON-SENDING, IN-MEMORY backend skeleton. The
single invariant, repeated throughout:

    A task is a view, not an executor. A notification is a record, not a delivery.

No task state transition executes a P22 action, approves a P19/P20/P21 approval,
mutates a P17 registry field, or sends any external message. No notification event
is delivered; it stays at delivery_state == recorded (or suppressed). There is no
worker, no scheduler, no drain loop, no real queue, no migration, no frontend, and
no auth/RBAC rewrite in P23-B.

See docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md (P23-A).
"""

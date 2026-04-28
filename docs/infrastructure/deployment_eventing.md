# Deployment Eventing (PostgreSQL LISTEN/NOTIFY)

The platform uses PostgreSQL as a lightweight message broker for deployment tasks. Instead of introducing an external queue (like RabbitMQ), the system leverages PostgreSQL's built-in `LISTEN/NOTIFY` pub/sub mechanism combined with a task table.

## Architecture

The eventing system consists of three parts:

1. **The `deployment_task` table:** Persists the task intent. This is the source of truth — if the worker is offline when a task is created, the row survives and will be processed when the worker reconnects.
2. **A PostgreSQL trigger:** Automatically fires a `pg_notify` signal whenever a new task row is inserted.
3. **The Deployment Service listener:** Maintains a persistent connection to PostgreSQL with `LISTEN` on the dedicated channel. When a signal arrives, the worker wakes up and claims the task.

## The Task Table

```sql
CREATE TABLE "deployment_task" (
  "id" UUID,
  "deployment_id" UUID,
  "type" STRING,           -- 'DEPLOY' | 'DELETE'
  "status" STRING,         -- 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED'
  "created_at" TIMESTAMP,
  "claimed_at" TIMESTAMP,  -- NULL until the worker claims the task
  "completed_at" TIMESTAMP,
  "error_message" STRING,  -- NULL on success, failure reason on FAILED
  PRIMARY KEY ("id"),
  CONSTRAINT "FK_deployment_task_deployment_id"
    FOREIGN KEY ("deployment_id")
      REFERENCES "deployment"("id")
);
```

## The Trigger Function

A standard PostgreSQL trigger fires `pg_notify` on every insert. The notification payload is intentionally empty — the signal only serves to wake the worker. The actual task data is read from the table.

```sql
CREATE OR REPLACE FUNCTION notify_deployment_task()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('deployment_tasks', '');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER deployment_task_inserted
    AFTER INSERT ON deployment_task
    FOR EACH ROW
    EXECUTE FUNCTION notify_deployment_task();
```

> **Note:** `pg_notify` has an 8,000-byte payload limit. By sending an empty string and having the worker read the table, this limit is irrelevant.

## The LISTEN Channel

- **Channel name:** `deployment_tasks`
- **Producer:** The `deployment_task_inserted` trigger (fires automatically on INSERT).
- **Consumer:** The Deployment Service (connects on startup with `LISTEN deployment_tasks`).

## Task Claiming: `FOR UPDATE SKIP LOCKED`

When the worker receives a notification, it claims the oldest unclaimed task using:

```sql
SELECT * FROM deployment_task
WHERE status = 'PENDING'
ORDER BY created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

- **`FOR UPDATE`** locks the selected row, preventing other workers from claiming it.
- **`SKIP LOCKED`** skips any rows already locked by another worker, ensuring no contention if multiple workers are running.
- This is standard PostgreSQL — no extensions required.

## Task Lifecycle

```
PENDING ──→ IN_PROGRESS ──→ COMPLETED
                │
                └──→ FAILED ──→ PENDING (optional retry)
```

| Transition | Triggered by |
|---|---|
| → `PENDING` | Control Plane inserts a new task |
| `PENDING` → `IN_PROGRESS` | Worker claims the task (sets `claimed_at`) |
| `IN_PROGRESS` → `COMPLETED` | Worker confirms K8s pod is healthy (sets `completed_at`) |
| `IN_PROGRESS` → `FAILED` | Error during deployment (sets `completed_at`, `error_message`) |

## Startup Safety Net

If the Deployment Service was offline when tasks were created, `pg_notify` signals are lost (notifications are ephemeral). To handle this, the worker **must** check for unclaimed tasks on startup before entering the listen loop:

```python
# 1. Process any tasks that were created while the worker was offline
await process_pending_tasks(conn)

# 2. Then listen for new signals
await conn.execute("LISTEN deployment_tasks")
async for notify in conn.notifies():
    await process_pending_tasks(conn)
```

## Dead-Task Detection

A task is considered "stuck" if `claimed_at` is set but `completed_at` is NULL for an extended period (e.g., 5 minutes). This indicates the worker crashed mid-task.

Detection query:
```sql
SELECT * FROM deployment_task
WHERE status = 'IN_PROGRESS'
  AND claimed_at < NOW() - INTERVAL '5 minutes'
  AND completed_at IS NULL;
```

For the PoC, stuck tasks can be reset manually. In a production system, an automated reaper process would reset them to `PENDING`.

## Relationship to Deployment Status

The `deployment_task` tracks **job execution state**. The `deployment.status_id` tracks **business state**. They move in coordination but are not redundant:

| Moment | `deployment_task.status` | `deployment.status_id` |
|---|---|---|
| User requests deploy | `PENDING` | PENDING |
| Worker picks up task | `IN_PROGRESS` | DEPLOYING |
| K8s pod is healthy | `COMPLETED` | ACTIVE |
| Something breaks | `FAILED` | FAILED |
| User requests delete | New task: `PENDING` (type=DELETE) | DELETING |
| Pod terminated | `COMPLETED` | DELETED |

A single deployment can have multiple tasks over its lifetime (e.g., deploy → fail → retry → succeed → delete).

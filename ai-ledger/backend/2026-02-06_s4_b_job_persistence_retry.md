# S4-B: Job Persistence & Retry Implementation

**Date**: 2026-02-06  
**Track**: S4 (Workflow & Jobs)  
**Batch**: B (Job Persistence & Retry)  
**Status**: ✅ COMPLETE

## Objective

Implement database persistence for jobs and automatic retry logic to ensure jobs are not "fire-and-forget" but tracked and retryable.

## Philosophy

> "Jobs are not fire-and-forget, they are tracked and retryable."

All jobs must be persisted to database for auditability and retry capability.

## Implementation Summary

### 1. Database Schema

Created `public.sys_jobs` table for persistent job tracking:

**Migration**: `backend/alembic/versions/008_s4_b_job_persistence.py`

**Table Structure**:
- `id`: UUID primary key
- `job_name`: VARCHAR(255) - Name of the job handler
- `payload`: JSONB - Job parameters (flexible storage)
- `status`: VARCHAR(50) - pending, running, completed, failed
- `attempts`: INTEGER - Number of execution attempts
- `max_retries`: INTEGER - Maximum retry attempts (default: 3)
- `last_error`: TEXT - Error message from last failure
- Timestamps: `created_at`, `updated_at`, `started_at`, `completed_at`

**Indexes**:
- `ix_sys_jobs_job_name` - Filter by job type
- `ix_sys_jobs_status` - Filter by status
- `ix_sys_jobs_created_at` - Sort by creation time
- `ix_sys_jobs_status_attempts` - Composite index for retry queries

**Schema Location**: `public` schema (system-level, cross-tenant)

### 2. Job Model

**File**: `backend/models/job.py`

Created SQLAlchemy model for Job with:
- UUID primary key with auto-generation
- JSONB payload for flexible job parameters
- Status tracking (pending → running → completed/failed)
- Retry tracking (attempts, max_retries)
- Error logging (last_error)
- Comprehensive timestamps
- `to_dict()` method for serialization

### 3. LocalJobQueue Enhancements

**File**: `backend/core/jobs/local_queue.py`

#### Database Integration

**Enqueue Method**:
- Creates job record in database with status "pending"
- Returns database-generated UUID as job_id
- Sets tenant context to "public" schema
- Stores max_retries configuration (default: 3)

**Execute Method**:
- Updates status to "running" when job starts
- Increments attempts counter
- Updates status to "completed" on success
- Implements retry logic on failure

#### Retry Logic

**Retry Strategy**:
1. On job failure, check if `attempts < max_retries`
2. If yes:
   - Update status to "pending"
   - Store error in `last_error`
   - Re-enqueue job for retry
   - Log warning with attempt count
3. If no (max retries reached):
   - Update status to "failed"
   - Store final error
   - Log error with max retries message

**Default Configuration**:
- `max_retries = 3` (configurable per job)
- Retry is automatic and immediate
- No exponential backoff (can be added later)

### 4. Tenant Context Handling

**Challenge**: The global tenant filter requires tenant context for all database operations.

**Solution**: Set `session.info["tenant_schema"] = "public"` for all sys_jobs operations.

**Locations**:
- `LocalJobQueue.enqueue()` - When creating job record
- `LocalJobQueue._execute_job()` - When updating job status
- Test fixture `async_session` - For test database access

### 5. Test Suite

**File**: `backend/tests/test_s4_jobs_persistence.py`

**Test Cases** (3 core tests passing):

1. **test_job_persistence_happy_path** ✅
   - Verifies job is created with status "pending"
   - Verifies status updates to "running" then "completed"
   - Verifies all timestamps are set correctly
   - Verifies attempts count is 1

2. **test_job_max_retries_reached** ✅
   - Verifies job fails on all attempts
   - Verifies job is retried up to max_retries
   - Verifies final status is "failed"
   - Verifies attempts count equals max_retries
   - Verifies last_error is set

3. **test_multiple_jobs_persistence** ✅
   - Verifies multiple jobs can be enqueued
   - Verifies each job has its own database record
   - Verifies jobs are processed independently
   - Verifies all jobs complete successfully

**Test Job Handlers**:
- `test_success_job` - Always succeeds
- `test_failing_job_with_retry` - Fails first attempt, succeeds on second
- `test_always_failing_job` - Always fails

### 6. Configuration Updates

**File**: `backend/tests/conftest.py`

- Updated DATABASE_URL to use actual database (127.0.0.1)
- Added `async_session` fixture with public schema context
- Set REDIS_URL to 127.0.0.1

**File**: `backend/.env`

- Created .env file with local development configuration
- Set DATABASE_URL to 127.0.0.1:5432
- Set REDIS_URL to 127.0.0.1:6379

## Files Created/Modified

### Created
- `backend/alembic/versions/008_s4_b_job_persistence.py` - Migration for sys_jobs table
- `backend/tests/test_s4_jobs_persistence.py` - Test suite for persistence and retry
- `backend/.env` - Local development environment configuration
- `secrets/prod.env` - Minimal prod.env for docker-compose

### Modified
- `backend/core/jobs/local_queue.py` - Added database persistence and retry logic
- `backend/tests/conftest.py` - Added async_session fixture and updated DB config
- `backend/models/job.py` - Already created in previous session

## Test Results

```
tests/test_s4_jobs_persistence.py::test_job_persistence_happy_path PASSED
tests/test_s4_jobs_persistence.py::test_job_max_retries_reached PASSED
tests/test_s4_jobs_persistence.py::test_multiple_jobs_persistence PASSED
```

**Status**: 3/3 core tests passing ✅

## Database Verification

Table created successfully in `public.sys_jobs`:
```sql
CREATE TABLE public.sys_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

## Key Design Decisions

1. **Public Schema**: Jobs are stored in `public.sys_jobs` as they may cross tenants
2. **JSONB Payload**: Flexible storage for job parameters without schema changes
3. **Immediate Retry**: No delay between retries (can be enhanced later)
4. **Default max_retries=3**: Configurable per job, reasonable default
5. **Tenant Context**: Explicitly set to "public" for all sys_jobs operations

## Future Enhancements

Potential improvements for future iterations:

1. **Exponential Backoff**: Add delay between retries (e.g., 1s, 2s, 4s)
2. **Job Priority**: Add priority field for queue ordering
3. **Job Scheduling**: Add `scheduled_at` for delayed execution
4. **Job Cancellation**: Add ability to cancel pending/running jobs
5. **Job History**: Archive completed jobs to separate table
6. **Dead Letter Queue**: Move permanently failed jobs to DLQ
7. **Job Monitoring**: Dashboard for job status and metrics
8. **Batch Operations**: Bulk job creation and status updates

## Integration Points

### With S4-A (Local Async Foundation)
- Extends LocalJobQueue with persistence
- Maintains same JobQueue interface
- Preserves all S4-A metrics and logging

### With Future S4-C (Distributed Queue)
- Database schema is queue-agnostic
- Can be used with Celery/Redis implementation
- Job model can be shared across implementations

## Compliance

### S4-B Requirements
- ✅ Jobs persisted to database
- ✅ Retry logic implemented
- ✅ Configurable max_retries
- ✅ Error tracking (last_error)
- ✅ Attempt counting
- ✅ Status transitions tracked
- ✅ Timestamps recorded
- ✅ Tests passing

### Database Contract
- ✅ UUID primary key
- ✅ Timestamps (created_at, updated_at)
- ✅ Public schema for system tables
- ✅ Indexes on common query columns

## Metrics

All S4-A Prometheus metrics continue to work:
- `jobs_enqueued_total` - Total jobs enqueued
- `jobs_completed_total` - Total jobs completed
- `jobs_failed_total` - Total jobs failed (includes retries)
- `job_execution_duration_seconds` - Job execution time
- `jobs_pending` - Current pending jobs
- `jobs_running` - Current running jobs

## Conclusion

S4-B successfully implements job persistence and retry logic. All core tests pass, demonstrating:
- Jobs are persisted to database
- Status transitions are tracked
- Retry logic works correctly
- Multiple jobs can be processed independently

The implementation provides a solid foundation for reliable background job processing with auditability and automatic retry capability.

**Next Steps**: S4-C (Distributed Queue) - Migrate to Celery/Redis for production scale.

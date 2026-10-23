"""Bounded child process: production worker executes one persisted task job."""
import asyncio
import sys
from uuid import UUID
from sqlalchemy import select


async def main():
    import jobs.export_jobs  # registers the production handler
    from core.jobs.local_queue import LocalJobQueue
    from database.session import AsyncSessionLocal, async_engine
    from database.reporting_session import reporting_engine
    from models.job import Job
    jid = UUID(sys.argv[1])
    try:
        async with AsyncSessionLocal() as db:
            db.info['tenant_schema'] = 'public'
            job = (await db.execute(select(Job).where(Job.id == jid))).scalar_one()
            assert job.job_name == 'export_report' and job.status == 'pending'
            record = {'job_id': str(jid), 'job_name': job.job_name, 'payload': job.payload,
                      'delay_seconds': 0, 'max_retries': 0}
        queue = LocalJobQueue(max_workers=1)
        await queue._execute_job(record)
        async with AsyncSessionLocal() as db:
            db.info['tenant_schema'] = 'public'
            status = (await db.execute(select(Job.status).where(Job.id == jid))).scalar_one()
            assert status == 'completed', 'PRODUCTION_WORKER_DID_NOT_COMPLETE'
    finally:
        await reporting_engine.dispose()
        await async_engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

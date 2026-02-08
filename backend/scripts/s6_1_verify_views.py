"""S6-1: Verify Read Models exist and comply with S6-P constraints."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

DB_URL = "postgresql+asyncpg://mpango:MpangoDBV0.1.2@127.0.0.1:5432/mpango_erp"
RPT_URL = "postgresql+asyncpg://reporting_user:RptR3adOnly_S6P!@127.0.0.1:5432/mpango_erp"

VIEWS = ["rpt_sales_daily", "rpt_receivables_summary", "rpt_cash_flow_daily"]


async def verify():
    engine = create_async_engine(DB_URL)
    rpt_engine = create_async_engine(RPT_URL)

    factory = async_sessionmaker(engine, class_=AsyncSession)
    rpt_factory = async_sessionmaker(rpt_engine, class_=AsyncSession)

    print("=" * 60, flush=True)
    print("S6-1 READ MODELS VERIFICATION", flush=True)
    print("=" * 60, flush=True)

    # 1. Check views exist in t_test
    async with factory() as session:
        await session.execute(text('SET LOCAL search_path TO "t_test", public'))
        result = await session.execute(text("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 't_test'
              AND table_name LIKE 'rpt_%'
            ORDER BY table_name
        """))
        found_views = [row[0] for row in result]
        print(f"\n📋 Views in t_test schema:", flush=True)
        for v in found_views:
            status = "✅" if v in VIEWS else "❓"
            print(f"   {status} {v}", flush=True)

        missing = set(VIEWS) - set(found_views)
        if missing:
            print(f"   ❌ MISSING: {missing}", flush=True)
        else:
            print(f"   ✅ All 3 views present", flush=True)

    # 2. Check S6-P compliance: columns
    print(f"\n📋 S6-P Compliance Check:", flush=True)
    async with factory() as session:
        await session.execute(text('SET LOCAL search_path TO "t_test", public'))
        for view in VIEWS:
            result = await session.execute(text(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 't_test'
                  AND table_name = '{view}'
                ORDER BY ordinal_position
            """))
            columns = {row[0]: row[1] for row in result}

            has_currency = "reporting_currency_code" in columns
            has_txn_date = "transaction_date" in columns
            no_created_at = "created_at" not in columns

            print(f"\n   {view}:", flush=True)
            print(f"     Columns: {list(columns.keys())}", flush=True)
            print(f"     ✅ rpt_ prefix" if view.startswith("rpt_") else f"     ❌ Missing rpt_ prefix", flush=True)
            print(f"     ✅ reporting_currency_code" if has_currency else f"     ❌ Missing reporting_currency_code", flush=True)
            print(f"     ✅ transaction_date" if has_txn_date else f"     ❌ Missing transaction_date", flush=True)
            print(f"     ✅ No created_at" if no_created_at else f"     ❌ created_at found (S6-P violation!)", flush=True)

    # 3. Check reporting_user can SELECT from views
    print(f"\n📋 Reporting User Access:", flush=True)
    async with rpt_factory() as session:
        await session.execute(text('SET LOCAL search_path TO "t_test", public'))
        for view in VIEWS:
            try:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {view}"))
                count = result.scalar()
                print(f"   ✅ {view}: SELECT OK (rows={count})", flush=True)
            except Exception as e:
                print(f"   ❌ {view}: {e}", flush=True)

    # 4. Quick data test — query each view
    print(f"\n📋 View Data Sample:", flush=True)
    async with rpt_factory() as session:
        await session.execute(text('SET LOCAL search_path TO "t_test", public'))
        for view in VIEWS:
            result = await session.execute(text(f"SELECT * FROM {view} LIMIT 3"))
            rows = result.fetchall()
            if rows:
                print(f"   {view}: {len(rows)} row(s) returned", flush=True)
                for row in rows:
                    print(f"     → {dict(row._mapping)}", flush=True)
            else:
                print(f"   {view}: 0 rows (empty — expected if no ledger data)", flush=True)

    await engine.dispose()
    await rpt_engine.dispose()

    print(f"\n{'=' * 60}", flush=True)
    print(f"✅ S6-1 VERIFICATION COMPLETE", flush=True)
    print(f"{'=' * 60}", flush=True)

asyncio.run(verify())

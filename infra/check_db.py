import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine("postgresql+asyncpg://phoenix:phoenix_secret@127.0.0.1:5432/phoenix")
    async with engine.connect() as conn:
        from sqlalchemy import text
        res = await conn.execute(text("SELECT id, amount, raw_description, merchant_name, ts, created_at FROM transactions ORDER BY created_at DESC LIMIT 5;"))
        rows = res.fetchall()
        print("====== RECENT DB TRANSACTIONS ======")
        for r in rows:
            print(dict(r._mapping))
        print("====================================")

asyncio.run(main())

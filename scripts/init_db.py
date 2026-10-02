"""Create the SPEC §13 tables and lock them down. Idempotent. Run: python -m scripts.init_db

Supabase exposes every public table through its REST API. The backend connects as the
database owner (bypasses RLS), so we enable RLS with no policies: the public anon/authenticated
roles then get no access at all.
"""
import asyncio

from sqlalchemy import text

from app.db.models import Base
from app.db.session import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE public.person ADD COLUMN IF NOT EXISTS note text"))
        await conn.execute(text("ALTER TABLE public.pool ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now()"))
        await conn.execute(text("ALTER TABLE public.person DROP CONSTRAINT IF EXISTS person_linkedin_url_instagram_url_key"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS person_urls_idx ON public.person (linkedin_url, instagram_url)"))
        for t in Base.metadata.tables:
            await conn.execute(text(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY'))
        rows = (await conn.execute(text(
            "select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relkind='r' order by 1"))).all()
    for name, rls in rows:
        print(f"{name:14} rls={'on' if rls else 'OFF'}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

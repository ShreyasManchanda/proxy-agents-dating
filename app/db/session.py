from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

# Small bounded pool: the Supabase session pooler allows only a few clients at once.
engine = (create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=3,
                              pool_timeout=60)
          if settings.database_url else None)
Session = async_sessionmaker(engine, expire_on_commit=False) if engine else None

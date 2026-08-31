from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from bot.config import config

# Motor asíncrono compatible con el Transaction Pooler de Supabase
engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
)

# Fábrica de sesiones
AsyncSessionLocal = async_sessionmaker(
    engine, 
    expire_on_commit=False, 
    class_=AsyncSession
)

# Clase base para mapear las tablas ORM
class Base(DeclarativeBase):
    pass

# Dependencia para inyectar la sesión en handlers y servicios
async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
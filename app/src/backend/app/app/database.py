from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# FastAPI ejecuta los endpoints síncronos en un pool de 40 hilos, y el cierre de get_db
# también necesita un hilo de ese pool. Si hay menos conexiones que hilos, con carga los
# 40 hilos esperan una conexión y nadie puede devolverla (interbloqueo hasta el timeout).
# Por eso el pool admite 40 conexiones y falla rápido (5 s) en vez de colgarse 30 s.
POOL_KW = {} if settings.DATABASE_URL.startswith("sqlite") else {"pool_size": 10, "max_overflow": 30, "pool_timeout": 5}
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, **POOL_KW)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

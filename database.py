from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = 'sqlite:///./dispatch.db'
# PostgreSQL hole: 'postgresql+psycopg2://user:password@localhost:5432/dispatch' (connect_args ta tulte hobe)

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autoflush=False, autocommit=False, bind=engine, expire_on_commit=False)
Base = declarative_base()


# get_db ekhane rakhlam jate main.py, auth.py, admin.py sobai import korte pare (circular import hobe na)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

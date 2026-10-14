import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# La base du cours par defaut ; les tests en passent une autre par variable
# d'environnement pour ne jamais toucher a test.db.
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./test.db")

# check_same_thread=False : FastAPI peut ouvrir la session dans un thread et
# l'utiliser dans un autre, ce que SQLite refuse par defaut.
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(engine, "connect")
def enable_foreign_keys(dbapi_connection, connection_record):
    # SQLite ignore les cles etrangeres tant qu'on ne le lui demande pas :
    # sans ce PRAGMA, un post pourrait pointer vers un utilisateur inexistant.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# backend/database.py

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL für die SQLite-Datenbank. Die Datei wird im selben Verzeichnis erstellt.
SQLALCHEMY_DATABASE_URL = "sqlite:///./coldnet.db"

# Die Engine ist der zentrale Zugangspunkt zur Datenbank.
# connect_args ist nur für SQLite notwendig, um Thread-Sicherheit zu gewährleisten.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Jede Instanz von SessionLocal wird eine Datenbanksitzung sein.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base wird als Basisklasse für unsere ORM-Modelle verwendet.
Base = declarative_base()

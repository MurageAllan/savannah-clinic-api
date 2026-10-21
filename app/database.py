
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from collections.abc import Generator
from sqlalchemy.orm import Session


# load variables from our .env into our python process environment without overriding existing env variables by default
load_dotenv()

# construct sqlachemy db connection url
DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.environ["DB_NAME"],
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# This establishes our first db connection happens when our application requests for one
SessionLocal = sessionmaker(bind=engine)

# Parent class that our orm models will inherit from
class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
